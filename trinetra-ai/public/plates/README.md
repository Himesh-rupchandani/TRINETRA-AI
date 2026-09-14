# Provided Evidence Images

Place the **exact** user-provided images here with these exact filenames (case-sensitive):

- `RJ19CL5074.jpg`  — white Hyundai i20 front (RJ19CL5074)
- `GJ03HK2595.jpg`  — silver Hyundai i10 rear, damaged bumper (GJ03HK2595)
- `GJ03NB2146.jpg`  — dark grey Alto K10 rear (GJ03NB2146)
- `GJ03JL5362.jpg`  — dark grey Baleno front (GJ03JL5362)
- `GJ03JL2801.jpg`  — grey Suzuki front (GJ03JL2801)

When you search any of those number plates in **Vehicle Log** (`/events?plate=...`), **Find a Vehicle** (`/vehicles`), or **Vehicle Investigation** (`/vehicles/<plate>`), every captured frame for that plate will show **this exact photo** (frame + plate crop) in the gallery and in the inline thumbnails.

The code checks for `/plates/<PLATE>.jpg` first — if present it is used with `synthetic:false`; otherwise it falls back to the synthetic SVG frame (demo mode). No AI-generated substitutes are used.

To install the images quickly (faster & proper):
```bash
# from repo root, after placing files in /tmp or Downloads:
cp /path/to/RJ19CL5074.jpg trinetra-ai/public/plates/RJ19CL5074.jpg
cp /path/to/GJ03HK2595.jpg trinetra-ai/public/plates/GJ03HK2595.jpg
cp /path/to/GJ03NB2146.jpg trinetra-ai/public/plates/GJ03NB2146.jpg
cp /path/to/GJ03JL5362.jpg trinetra-ai/public/plates/GJ03JL5362.jpg
cp /path/to/GJ03JL2801.jpg trinetra-ai/public/plates/GJ03JL2801.jpg
npm --prefix trinetra-ai run build  # optional, images are static
```

All galleries use lazy + async decode, fixed aspect thumbnails, and instant modal previews — so Vehicle Log remains fast even with real photos.
