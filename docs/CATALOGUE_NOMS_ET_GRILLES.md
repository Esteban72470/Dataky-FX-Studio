# Catalogue names and grids

The visual review added 1,447 descriptive French names to entries with blank or generic names. The previous names remain as aliases, and the Roblox IDs are preserved. The review identified 1,428 names from images and used category-based names for the 19 entries with unavailable images.

The review covered all 98 flipbooks without a known layout. It confirmed 74 grids of 4×4, 13 of 8×8, six of 2×2, and one of 6×4 (`79593708822934`). The catalogue displays and animates the rectangular grid. The editor applies it with `FlipbookLayout=Custom`, `FlipbookSizeX=6`, and `FlipbookSizeY=4`.

Previews for `17387207972`, `110361796788602`, and `77966646561127` are unavailable. The source data classifies image `15054104862` (Bats) ambiguously, and the image has no visible regular grid. All four entries retain an unknown layout.

`tool/catalog_annotations_data.py` stores the corrections. `tool/catalog_annotations.py` reads that file as data without executing it. It records where the names came from, the verified dimensions, and image hashes. The raw captures stay intact. Catalogue rebuilds and read APIs reapply the corrections so they survive updates.
