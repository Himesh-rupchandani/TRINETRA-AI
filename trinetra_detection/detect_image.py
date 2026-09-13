"""
Run Vehicle and Number Plate Detection on Images.
Usage:
    python detect_image.py --input sample_data/sample_1.jpg
    python detect_image.py --input sample_data/
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
import cv2
from core.detector import VehiclePlateDetector
from core.visualizer import Visualizer


def process_image(
    image_path: Path,
    detector: VehiclePlateDetector,
    output_dir: Path,
    plates_dir: Path,
    conf: float,
    imgsz: int = 960,
):
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"[Warning] Could not read image: {image_path}")
        return

    detections = detector.detect(image, conf=conf, imgsz=imgsz)
    vehicles = detector.filter_by_class(detections, "vehicle")
    plates = detector.filter_by_class(detections, "number_plate")

    print(f"\n[Image] {image_path.name}")
    print(f"  -> Vehicles Detected : {len(vehicles)}")
    print(f"  -> Plates Detected   : {len(plates)}")

    # Crop and save detected license plates
    stem = image_path.stem
    for i, plate in enumerate(plates):
        plate_crop = plate.crop(image)
        if plate_crop.size > 0:
            crop_name = f"{stem}_plate_{i+1}_conf{int(plate.confidence*100)}.jpg"
            crop_path = plates_dir / crop_name
            cv2.imwrite(str(crop_path), plate_crop)
            print(f"  [Saved Plate Crop] {crop_name} (Conf: {plate.confidence:.2f})")

    # Annotate and save image
    annotated = Visualizer.draw_detections(image, detections)
    info = f"Vehicles: {len(vehicles)} | Plates: {len(plates)}"
    annotated = Visualizer.draw_banner(annotated, title="TRINETRA AI", info_text=info)

    out_file = output_dir / f"{stem}_detected.jpg"
    cv2.imwrite(str(out_file), annotated)
    print(f"  [Saved Annotated] -> {out_file.name}")


def main():
    parser = argparse.ArgumentParser(description="Trinetra AI Image Detection")
    parser.add_argument(
        "--input",
        default="sample_data",
        help="Path to an image file or directory containing images",
    )
    parser.add_argument(
        "--model",
        default="models/best.pt",
        help="Path to YOLO weights (default: models/best.pt)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.35,
        help="Confidence threshold (default: 0.35)",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.45,
        help="NMS IoU threshold (default: 0.45) - removes double boxes",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=960,
        help="Inference resolution (default: 960; small/distant vehicles need it)",
    )
    parser.add_argument(
        "--vehicle-model",
        default=None,
        help="Per-class weight for VEHICLE boxes ('none' = keep using --model)",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/annotated_images",
        help="Directory to save annotated images",
    )
    parser.add_argument(
        "--plates-dir",
        default="outputs/detected_plates",
        help="Directory to save cropped license plates",
    )
    parser.add_argument("--no-multiscale", action="store_true",
                        help="Skip the native-resolution second pass (faster, looser boxes)")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    input_path = (base_dir / args.input) if not os.path.isabs(args.input) else Path(args.input)
    output_dir = (base_dir / args.output_dir) if not os.path.isabs(args.output_dir) else Path(args.output_dir)
    plates_dir = (base_dir / args.plates_dir) if not os.path.isabs(args.plates_dir) else Path(args.plates_dir)
    model_path = (base_dir / args.model) if not os.path.isabs(args.model) else Path(args.model)

    output_dir.mkdir(parents=True, exist_ok=True)
    plates_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)

    print("=" * 65)
    print("  TRINETRA AI - Vehicle & Number Plate Detection")
    print("=" * 65)
    print(f"  Input       : {input_path}")
    print(f"  Model       : {model_path}")
    print(f"  Confidence  : {args.conf}")
    print(f"  NMS IoU     : {args.iou}")
    print(f"  Img size    : {args.imgsz}")
    print(f"  Multi-scale : {'off' if args.no_multiscale else 'on'}")
    print("=" * 65)

    detector = VehiclePlateDetector(
        model_path=str(model_path),
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        imgsz=args.imgsz,
        vehicle_model_path=args.vehicle_model,
        multiscale=not args.no_multiscale,
    )
    print(f"  Vehicle wt  : {detector.vehicle_model_path or model_path}")

    valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if input_path.is_file():
        process_image(input_path, detector, output_dir, plates_dir, args.conf, args.imgsz)
    else:
        images = [p for p in input_path.iterdir() if p.suffix.lower() in valid_extensions]
        if not images:
            print(f"No valid images found in: {input_path}")
            sys.exit(0)
        print(f"Found {len(images)} image(s) to process...")
        for img_path in images:
            process_image(img_path, detector, output_dir, plates_dir, args.conf, args.imgsz)

    print("\n" + "=" * 65)
    print(f"  COMPLETED! Annotated outputs saved to: {output_dir}")
    print(f"  Cropped license plates saved to:       {plates_dir}")
    print("=" * 65)


if __name__ == "__main__":
    main()
