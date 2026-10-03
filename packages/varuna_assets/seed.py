"""Illustrative Indian Coast Guard fleet/personnel seed data (Phase 4).

Ported directly from `frontend/VARUNA-frontend_yash/app/assets/page.tsx`'s
previously-hardcoded, disconnected `PATROL_VESSELS`/`AIRCRAFT` arrays — so
that already-well-formed mock data becomes the real backend seed instead of
staying a second, disconnected source of truth. `SENSORS` (satellites, AIS
receivers, VTMS) are NOT ported here — they aren't assignable response
assets in the `AssetKind` sense, and stay as informational-only content on
the frontend page.

Explicitly illustrative, not a real personnel/fleet feed — see
`varuna_contracts.assets` module docstring. Ranks and names are
representative Indian Coast Guard convention, not real individuals.
"""
from __future__ import annotations

from varuna_contracts.assets import Asset, AssetKind, AssetStatus, DutyPersonnel, DutyRole

SEED_ASSETS: list[Asset] = [
    Asset(asset_id="ICGS-VARAD", name="ICGS Varad", kind=AssetKind.OPV,
          home_base="Mumbai", status=AssetStatus.DEPLOYED,
          notes="Arabian Sea — Sector 4A", endurance_hours=240, crew_size=110),
    Asset(asset_id="ICGS-SHAURYA", name="ICGS Shaurya", kind=AssetKind.FPV,
          home_base="Porbandar", status=AssetStatus.AVAILABLE,
          notes="In port", endurance_hours=48, crew_size=35),
    Asset(asset_id="PV-01-INTERCEPTOR", name="PV-01 Interceptor", kind=AssetKind.INTERCEPTOR_BOAT,
          home_base="Goa", status=AssetStatus.AVAILABLE,
          notes="In port", endurance_hours=12, crew_size=8),
    Asset(asset_id="PV-03-INTERCEPTOR", name="PV-03 Interceptor", kind=AssetKind.INTERCEPTOR_BOAT,
          home_base="Mumbai Harbor", status=AssetStatus.AVAILABLE,
          notes="In port", endurance_hours=12, crew_size=8),
    Asset(asset_id="ICGS-RAJVEER", name="ICGS Rajveer", kind=AssetKind.OPV,
          home_base="Kochi", status=AssetStatus.DEPLOYED,
          notes="Lakshadweep Sea", endurance_hours=240, crew_size=110),
    Asset(asset_id="PV-05-FAST-PATROL", name="PV-05 Fast Patrol", kind=AssetKind.FPV,
          home_base="Chennai", status=AssetStatus.MAINTENANCE,
          notes="In drydock", endurance_hours=48, crew_size=35),
    Asset(asset_id="AIRCRAFT-01", name="Aircraft-01", kind=AssetKind.DORNIER_228,
          home_base="INS Hansa, Goa", status=AssetStatus.DEPLOYED,
          endurance_hours=6, crew_size=4),
    Asset(asset_id="AIRCRAFT-02", name="Aircraft-02", kind=AssetKind.DORNIER_228,
          home_base="INS Hansa, Goa", status=AssetStatus.AVAILABLE,
          endurance_hours=6, crew_size=4),
    Asset(asset_id="AIRCRAFT-03", name="Aircraft-03", kind=AssetKind.RUAV_HERON,
          home_base="Porbandar", status=AssetStatus.AVAILABLE,
          endurance_hours=18, crew_size=0),
]

SEED_PERSONNEL: list[DutyPersonnel] = [
    DutyPersonnel(personnel_id="DO-MUMBAI-01", name="Cdr. A. Krishnan", rank="Commandant",
                  role=DutyRole.DUTY_OFFICER, base="Mumbai", on_duty=True),
    DutyPersonnel(personnel_id="DO-PORBANDAR-01", name="Lt. Cdr. R. Iyer", rank="Deputy Commandant",
                  role=DutyRole.DUTY_OFFICER, base="Porbandar", on_duty=True),
    DutyPersonnel(personnel_id="DO-KOCHI-01", name="Lt. Cdr. S. Menon", rank="Deputy Commandant",
                  role=DutyRole.DUTY_OFFICER, base="Kochi", on_duty=False),
    DutyPersonnel(personnel_id="SUP-MUMBAI-01", name="Capt. V. Rao", rank="Commandant (Senior)",
                  role=DutyRole.SUPERVISOR, base="Mumbai", on_duty=True),
    DutyPersonnel(personnel_id="FO-GOA-01", name="Asst. Cdt. N. Sharma", rank="Assistant Commandant",
                  role=DutyRole.FIELD_OPERATOR, base="Goa", on_duty=True),
    DutyPersonnel(personnel_id="FO-CHENNAI-01", name="Asst. Cdt. P. Nair", rank="Assistant Commandant",
                  role=DutyRole.FIELD_OPERATOR, base="Chennai", on_duty=True),
]
