import struct

HEADER = b"QTI Chromatix Header"
PARSER_V2 = b"Parameter Parser V2.0.0"
SYMBOL = struct.Struct("<Q32sQQQQ")


def parse(blob):
    if not blob.startswith(HEADER) or len(blob) < 0xD0:
        raise ValueError("not a CamX module file")
    table, table_size = struct.unpack_from("<QQ", blob, 0xA8)
    data, data_size = struct.unpack_from("<QQ", blob, 0xC0)
    if table + table_size > len(blob) or data + data_size > len(blob):
        raise ValueError("truncated CamX module file")
    symbols = []
    for offset in range(table, table + table_size - SYMBOL.size + 1, SYMBOL.size):
        sid, name, kind, parent, start, size = SYMBOL.unpack_from(blob, offset)
        symbols.append(
            (sid, name.split(b"\0")[0].decode("latin1"), kind, parent, start, size)
        )
    return blob[data : data + data_size], symbols
