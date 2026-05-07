import json, argparse
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--landmarks", required=True)
    args = ap.parse_args()
    with open(args.landmarks, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[import_landmarks] frames={len(data.get('frames', []))}, joints={len(data.get('names', []))}")
if __name__ == "__main__":
    main()