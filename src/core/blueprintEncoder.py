def encode_blueprint(blueprint):
    """
    Encode the blueprint into a Factorio-compatible string.
    """
    import json
    import zlib
    import base64

    blueprint_json = json.dumps(blueprint)
    compressed_data = zlib.compress(blueprint_json.encode())
    return "0" + base64.b64encode(compressed_data).decode()
