import zlib
import base64
import json

def decode_blueprint(base64_string):
    # Step 1: Remove the first character (it's part of the Factorio encoding)
    compressed_data = base64.b64decode(base64_string[1:])
    
    # Step 2: Decompress the zlib-compressed data
    decompressed_data = zlib.decompress(compressed_data)
    
    # Step 3: Convert the byte string back to JSON
    blueprint_json = json.loads(decompressed_data)
    
    return blueprint_json

# Example base64 encoded blueprint string
blueprint_string = input("Enter a Factorio blueprint string: ")

# Decode the blueprint string
decoded_blueprint = decode_blueprint(blueprint_string)

# Pretty-print the JSON
print(json.dumps(decoded_blueprint, indent=4))
