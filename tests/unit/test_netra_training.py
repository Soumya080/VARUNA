import pytest
import os
from varuna_netra.model.config import NetraModelConfig
from varuna_netra.model.factory import create_netra_model
from varuna_netra.training.config import NetraTrainingConfig
from varuna_netra.training.trainer import NetraTrainer
from varuna_netra.dataset.synthetic import SyntheticNetraDataset

def test_netra_training_loop(tmp_path):
    # Use synthetic dataset
    dataset = SyntheticNetraDataset(num_samples=10, seed=42)
    train_samples = dataset.list_samples(split="train")
    val_samples = dataset.list_samples(split="val")
    
    # Create model
    model_config = NetraModelConfig(encoder_name="resnet18", classes=3)
    model = create_netra_model(model_config)
    
    # Create trainer
    checkpoint_dir = str(tmp_path / "models")
    train_config = NetraTrainingConfig(
        epochs=2, 
        batch_size=2, 
        checkpoint_dir=checkpoint_dir,
        seed=42
    )
    trainer = NetraTrainer(train_config)
    
    # Run training
    experiment_id = "test_exp_123"
    best_ckpt = trainer.train(model, train_samples, val_samples, experiment_id)
    
    assert os.path.exists(best_ckpt)
    assert best_ckpt.endswith(f"{experiment_id}_best.pt")
