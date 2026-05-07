import argparse
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--landmarks", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    print("[setup_scene] Configure Blender scene (stub).")
    print(f" video={args.video}\n landmarks={args.landmarks}\n out={args.out}")
if __name__ == "__main__":
    main()