"""Clip Meta/WRI Global Canopy Height (1 m, CC BY 4.0) to the pilot area.

Reads only the pilot window from the cloud-optimised GeoTIFF on the public AWS
bucket (HTTP range requests), and writes data/canopy_um.tif (gitignored).
Then run:  python scripts/build_comfort.py --canopy data/canopy_um.tif

Citation: Meta and World Resources Institute (WRI), 2024. High Resolution Canopy
Height Maps. Source imagery © 2016 Maxar.
"""

from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

TILE = ("https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/"
        "alsgedi_global_v6_float/chm/132232022.tif")  # quadkey of the UM area at zoom 9
BBOX = (101.637, 3.100, 101.673, 3.136)  # west, south, east, north
OUT = Path(__file__).resolve().parent.parent / "data" / "canopy_um.tif"


def main() -> None:
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif"}
    with rasterio.Env(**env), rasterio.open(f"/vsicurl/{TILE}") as src:
        print("source:", src.crs, src.dtypes[0], src.res, "overviews:", src.overviews(1))
        bounds = transform_bounds("EPSG:4326", src.crs, *BBOX)
        window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        data = src.read(1, window=window)
        profile = src.profile.copy()
        profile.update(width=data.shape[1], height=data.shape[0], transform=src.window_transform(window),
                       compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT, "w", **profile) as dst:
        dst.write(data, 1)
    print(f"wrote {OUT} {data.shape}  canopy>=3m: {(data >= 3).mean():.1%}")


if __name__ == "__main__":
    main()
