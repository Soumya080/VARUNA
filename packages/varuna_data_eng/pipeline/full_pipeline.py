from typing import Dict, List, Optional
import numpy as np

from varuna_contracts.evidence import TrustState
from varuna_data_eng.schemas.canonical_sar import CanonicalSAR
from varuna_data_eng.schemas.oil_mask import OilMask
from varuna_data_eng.schemas.ais import RawAISTrack
from varuna_data_eng.schemas.forcing import ForcingCube
from varuna_data_eng.schemas.attribution_case import AttributionCase
from varuna_data_eng.schemas.manifest import DatasetManifest, ManifestEntry, SplitManifest
from varuna_data_eng.schemas.provenance import TileRecord
from varuna_data_eng.pipeline.quality_engine import QualityEngine
from varuna_data_eng.pipeline.data_guard_v2 import DataGuardV2
from varuna_data_eng.pipeline.dedup_pipeline import DedupPipeline
from varuna_data_eng.pipeline.label_alignment import LabelAlignment
from varuna_data_eng.pipeline.split_engine import SplitEngine
from varuna_data_eng.pipeline.leakage_guard import LeakageGuard
from varuna_data_eng.pipeline.normalizer import Normalizer
from varuna_data_eng.pipeline.tiler import Tiler
from varuna_data_eng.pipeline.manifest_builder import ManifestBuilder
from varuna_data_eng.pipeline.array_provider import (
    TrainingArrayProvider,
    DeterministicSyntheticArrayProvider,
    FileBackedArrayProvider,
)
from varuna_data_eng.schemas.quality import DedupVerdict, DedupState


class FullPipeline:
    """Orchestrates the entire Data Engineering process (M6).

    Order is architecturally load-bearing:

        RAW -> QUALITY -> DATAGUARD -> DEDUP -> SPLIT -> TILE -> NORMALIZE -> MANIFEST

    A scene must clear DataGuard (not QUARANTINED) and dedup (KEEP) before it
    is eligible for a split assignment; only split-assigned entries are
    tiled; only TRAIN-split tiles/arrays feed normalization statistics.
    """

    def __init__(
        self,
        seed: int = 42,
        synthetic_mode: bool = False,
        split_strategy: str = "geographic_temporal",
        tile_size: int = 32,
        tile_stride: Optional[int] = None,
        array_provider: Optional[TrainingArrayProvider] = None,
    ):
        self.synthetic_mode = synthetic_mode
        self.quality = QualityEngine(synthetic_mode=synthetic_mode)
        self.guard = DataGuardV2(synthetic_mode=synthetic_mode)
        self.dedup = DedupPipeline()
        self.aligner = LabelAlignment()
        self.split_engine = SplitEngine(seed=seed, strategy=split_strategy)
        self.leakage = LeakageGuard()
        self.normalizer = Normalizer()
        self.tiler = Tiler(tile_size=tile_size, stride=tile_stride or tile_size)
        self.manifest = ManifestBuilder()
        self.array_provider = array_provider or (
            DeterministicSyntheticArrayProvider(seed=seed, shape=(tile_size * 2, tile_size * 2))
            if synthetic_mode
            else FileBackedArrayProvider()
        )
        # Populated by the most recent process_raw_dataset() call, for callers
        # that need tile-level provenance (e.g. training data loaders, tests).
        self.last_run_tiles: List[TileRecord] = []

    @staticmethod
    def _region_bin(sar: CanonicalSAR) -> str:
        """Coarse geographic bin derived from the scene's actual bbox center,
        so the "geographic"/"geographic_temporal" split strategies have real
        geography to group on end-to-end — not a constant placeholder that
        would collapse every scene into a single group.
        """
        center = sar.bbox.center
        lat_bin = int(center.lat // 5)
        lon_bin = int(center.lon // 5)
        return f"grid_{lat_bin}_{lon_bin}"

    def process_raw_dataset(
        self,
        dataset_id: str,
        dataset_version: str,
        sar_list: List[CanonicalSAR],
        mask_list: List[OilMask],
    ) -> DatasetManifest:
        """Processes an entire dataset down to a manifest."""
        # 1. Quality & Trust (DataGuard)
        entries: List[ManifestEntry] = []
        for sar in sar_list:
            q_state = self.quality.validate_sar(sar)
            trust_state = self.guard.evaluate(sar)

            if trust_state == TrustState.QUARANTINED:
                # Quarantined scenes never enter the manifest, never get
                # deduped/split/tiled/normalized — DataGuard is a hard gate.
                continue

            matched_mask = next((m for m in mask_list if m.scene_id == sar.scene_id), None)
            if matched_mask:
                self.aligner.align(sar, matched_mask)

            entries.append(ManifestEntry(
                sample_id=f"samp_{sar.scene_id}",
                scene_id=sar.scene_id,
                content_hash=sar.file_checksum,
                split="unassigned",
                sensor=sar.sensor.value if hasattr(sar.sensor, "value") else sar.sensor,
                region=self._region_bin(sar),
                acquisition_date=sar.acquisition_time,
                quality_state=q_state,
                dedup_state=DedupState(verdict=DedupVerdict.KEEP),  # overwritten below
                file_paths={"sar": sar.data_path},
            ))

        accepted_ids = {e.scene_id for e in entries}
        accepted_sar_list = [s for s in sar_list if s.scene_id in accepted_ids]

        # 2. Dedup — only among scenes that already cleared DataGuard
        dedup_results = self.dedup.process(accepted_sar_list)
        dedup_map = {sar.scene_id: state for sar, state in dedup_results}

        kept_entries = []
        for e in entries:
            e.dedup_state = dedup_map[e.scene_id]
            if e.dedup_state.verdict == DedupVerdict.KEEP:
                kept_entries.append(e)

        sar_map = {sar.scene_id: sar for sar in sar_list}

        # 3. Split — must happen before any tiling
        splits_dict = self.split_engine.split(kept_entries)

        # 4. Leakage check across every split pair (train/val, train/test, val/test)
        if not self.leakage.check_leakage(splits_dict, sar_map=sar_map):
            raise ValueError("Data Leakage detected!")

        split_manifest = SplitManifest(
            strategy=self.split_engine.strategy,
            group_key="scene_id",
            split_counts={k: len(v) for k, v in splits_dict.items()},
            seed=self.split_engine.seed,
            frozen_at=sar_list[0].acquisition_time if sar_list else None,
        )

        # 5. Tiling — only split-assigned, DataGuard-cleared, deduped entries
        #    ever produce tiles; a quarantined or duplicate scene has already
        #    been excluded from `kept_entries` and can never reach this step.
        self.last_run_tiles = []
        for entry in kept_entries:
            sar = sar_map[entry.scene_id]
            channels = self.array_provider.load_channels(sar)
            if not channels:
                continue
            primary_channel = sorted(channels)[0]
            tiles = self.tiler.tile_array(
                sar, channels[primary_channel], split=entry.split, source=dataset_id
            )
            entry.tile_ids = [t.tile_id for t in tiles]
            self.last_run_tiles.extend(tiles)

        # 6. Normalization — TRAIN split only, real (or deterministic
        #    synthetic) arrays, never a placeholder zero/empty array.
        train_entries = [e for e in kept_entries if e.split == "train"]
        if not train_entries:
            raise ValueError(
                "No training-split entries available; cannot compute normalization "
                "statistics from an empty train split."
            )

        collected: Dict[str, List[np.ndarray]] = {}
        for entry in train_entries:
            sar = sar_map[entry.scene_id]
            channel_arrays = self.array_provider.load_channels(sar)
            for ch, arr in channel_arrays.items():
                collected.setdefault(ch, []).append(arr)

        train_arrays = {ch: np.concatenate([a.ravel() for a in arrs]) for ch, arrs in collected.items()}
        norm_sensor = sar_map[train_entries[0].scene_id].sensor
        norm_sensor = norm_sensor.value if hasattr(norm_sensor, "value") else norm_sensor
        norm_record = self.normalizer.compute_stats(dataset_version, norm_sensor, train_arrays)
        # The same frozen record is attached once to the manifest and applies
        # to val/test as well — it is never recomputed per split or per tile.

        # 7. Manifest build — only kept_entries (DataGuard-cleared, deduped) included
        manifest = self.manifest.build(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            entries=kept_entries,
            splits=split_manifest,
            provenance=sar_list[0].provenance if sar_list else None,
            normalization_stats=norm_record,
        )
        return manifest
