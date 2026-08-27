import pytest
import os
from varuna_chhaya.model.config import ChhayaModelConfig
from varuna_chhaya.model.factory import create_chhaya_model
from varuna_chhaya.training.trainer import ChhayaTrainingConfig, ChhayaTrainer
from varuna_chhaya.dataset.synthetic import SyntheticChhayaDataset

def test_chhaya_training_loop(tmp_path):
    dataset = SyntheticChhayaDataset(num_samples=10, seed=42)
    train_samples = dataset.list_samples(split="train")
    val_samples = dataset.list_samples(split="val")
    
    model_config = ChhayaModelConfig(input_dim=4, output_dim=2)
    model = create_chhaya_model(model_config)
    
    checkpoint_dir = str(tmp_path / "chhaya_models")
    train_config = ChhayaTrainingConfig(
        epochs=2,
        checkpoint_dir=checkpoint_dir
    )
    trainer = ChhayaTrainer(train_config)
    
    experiment_id = "test_exp_chhaya"
    best_ckpt = trainer.train(model, train_samples, val_samples, experiment_id)
    
    assert os.path.exists(best_ckpt)
