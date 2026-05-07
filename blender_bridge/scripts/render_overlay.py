import argparse
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    print(f"[render_overlay] Render to {args.out}")
if __name__ == "__main__":
    main()