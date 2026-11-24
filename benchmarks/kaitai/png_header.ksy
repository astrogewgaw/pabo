meta:
  id: png_header
  endian: be
seq:
  - id: magic
    contents: [0x89, "PNG", 0x0d, 0x0a, 0x1a, 0x0a]
  - id: ihdr_size
    type: u4
  - id: ihdr_id
    contents: "IHDR"
  - id: width
    type: u4
  - id: height
    type: u4
