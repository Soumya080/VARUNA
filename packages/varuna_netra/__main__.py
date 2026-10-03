import argparse
import sys

def main():
    parser = argparse.ArgumentParser(prog="varuna_netra")
    subparsers = parser.add_subparsers(dest="command")
    
    train_p = subparsers.add_parser("train")
    train_p.add_argument("--config", required=True)
    train_p.add_argument("--data-manifest", required=True)
    train_p.add_argument("--seed", type=int, default=42)
    
    eval_p = subparsers.add_parser("evaluate")
    eval_p.add_argument("--checkpoint", required=True)
    eval_p.add_argument("--split", default="test")
    
    export_p = subparsers.add_parser("export")
    export_p.add_argument("--checkpoint", required=True)
    export_p.add_argument("--out", required=True)
    export_p.add_argument("--format", default="torchscript")
    
    args = parser.parse_args()
    
    if args.command == "train":
        print(f"Training with config {args.config} and seed {args.seed} (M5 stub)")
    elif args.command == "evaluate":
        print(f"Evaluating checkpoint {args.checkpoint} on {args.split} split (M5 stub)")
    elif args.command == "export":
        print(f"Exporting checkpoint {args.checkpoint} to {args.out} (M5 stub)")
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
