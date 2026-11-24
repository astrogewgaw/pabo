meta:
  id: records
  endian: le
seq:
  - id: items
    type: record
    repeat: expr
    repeat-expr: 1000
types:
  record:
    seq:
      - id: a
        type: u2
      - id: b
        type: u4
      - id: c
        type: f4
