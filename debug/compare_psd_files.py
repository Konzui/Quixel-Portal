"""
PSD File Comparison Script

This script compares two PSD files to identify differences in addon settings,
metadata, layers, annotations, and other properties that might have been
modified by Photoshop addons.

Usage:
    python compare_psd_files.py
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import json

try:
    from psd_tools import PSDImage
    from psd_tools.api.layers import Layer
    from psd_tools.constants import Tag
except ImportError:
    print("ERROR: psd-tools library is required.")
    print("Install it with: pip install psd-tools")
    sys.exit(1)


def extract_layer_info(layer: Layer, depth: int = 0) -> Dict[str, Any]:
    """Extract all information from a layer recursively."""
    info = {
        'name': layer.name,
        'kind': str(layer.kind) if hasattr(layer, 'kind') else None,
        'visible': layer.visible if hasattr(layer, 'visible') else None,
        'opacity': layer.opacity if hasattr(layer, 'opacity') else None,
        'blend_mode': str(layer.blend_mode) if hasattr(layer, 'blend_mode') else None,
        'bbox': tuple(layer.bbox) if hasattr(layer, 'bbox') else None,
        'size': tuple(layer.size) if hasattr(layer, 'size') else None,
        'offset': tuple(layer.offset) if hasattr(layer, 'offset') else None,
    }
    
    # Extract layer effects if available
    if hasattr(layer, 'effects'):
        effects = {}
        for effect_name in dir(layer.effects):
            if not effect_name.startswith('_'):
                try:
                    effect = getattr(layer.effects, effect_name)
                    if effect is not None:
                        effects[effect_name] = str(effect)
                except:
                    pass
        if effects:
            info['effects'] = effects
    
    # Extract layer metadata/tags
    if hasattr(layer, 'tagged_blocks'):
        tagged_blocks = {}
        for key, value in layer.tagged_blocks.items():
            try:
                # Convert to string representation for comparison
                if isinstance(value, bytes):
                    tagged_blocks[str(key)] = value.hex()[:100]  # First 100 hex chars
                else:
                    tagged_blocks[str(key)] = str(value)
            except:
                tagged_blocks[str(key)] = "<unserializable>"
        if tagged_blocks:
            info['tagged_blocks'] = tagged_blocks
    
    # Recursively extract child layers
    if hasattr(layer, 'layers'):
        children = []
        for child in layer.layers:
            children.append(extract_layer_info(child, depth + 1))
        if children:
            info['children'] = children
    
    return info


def try_decode_text(data: bytes) -> str:
    """Try to decode bytes as text, trying multiple encodings."""
    encodings = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'ascii']
    for encoding in encodings:
        try:
            decoded = data.decode(encoding, errors='ignore')
            # Check if it looks like readable text (not just random characters)
            if len(decoded) > 0 and any(c.isprintable() or c.isspace() for c in decoded[:100]):
                return decoded
        except:
            continue
    return None


def extract_enumerated_value(obj) -> Any:
    """Extract actual value from Enumerated object."""
    try:
        if hasattr(obj, 'value'):
            return obj.value
        if hasattr(obj, 'name'):
            return obj.name
        if hasattr(obj, 'enum'):
            return obj.enum
        # Try to get string representation
        return str(obj)
    except:
        return str(obj)


def extract_descriptor_block(obj) -> Dict[str, Any]:
    """Extract all data from a DescriptorBlock object."""
    result = {'_type': 'DescriptorBlock'}
    try:
        # Common DescriptorBlock attributes
        if hasattr(obj, 'items'):
            items = {}
            for key, value in obj.items():
                try:
                    # Convert bytes keys
                    if isinstance(key, bytes):
                        key_str = try_decode_text(key) or key.hex()[:50]
                    else:
                        key_str = str(key)
                    items[key_str] = deep_extract_value(value, max_depth=5, current_depth=0)
                except Exception as e:
                    items[str(key)] = f"<error: {e}>"
            if items:
                result['items'] = items
        
        # Try common attributes
        for attr in ['classID', 'name', 'ostype', 'version', 'data']:
            if hasattr(obj, attr):
                try:
                    result[attr] = deep_extract_value(getattr(obj, attr), max_depth=5, current_depth=0)
                except:
                    pass
    except Exception as e:
        result['_error'] = str(e)
    return result


def deep_extract_value(obj, max_depth: int = 3, current_depth: int = 0) -> Any:
    """Recursively extract values from complex objects."""
    if current_depth >= max_depth:
        return str(obj)
    
    # Handle basic types
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    
    # Handle bytes
    if isinstance(obj, bytes):
        decoded = try_decode_text(obj)
        if decoded:
            return {'type': 'bytes_text', 'text': decoded[:500], 'size': len(obj)}
        return {'type': 'bytes', 'hex': obj.hex()[:500], 'size': len(obj)}
    
    # Handle Enumerated objects
    if hasattr(obj, '__class__') and 'Enumerated' in str(type(obj)):
        return extract_enumerated_value(obj)
    
    # Handle DescriptorBlock objects
    if hasattr(obj, '__class__') and 'DescriptorBlock' in str(type(obj)):
        return extract_descriptor_block(obj)
    
    # Handle Slice objects
    if hasattr(obj, '__class__') and 'Slice' in str(type(obj)):
        result = {'_type': type(obj).__name__}
        try:
            for attr in ['name', 'groupID', 'origin', 'associatedLayerID', 'bounds', 'url', 'target', 'message', 'altTag', 'cellTextIsHTML', 'cellText', 'horizontalAlignment', 'verticalAlignment', 'alphaColor', 'red', 'green', 'blue', 'sliceID']:
                if hasattr(obj, attr):
                    try:
                        result[attr] = deep_extract_value(getattr(obj, attr), max_depth=3, current_depth=current_depth + 1)
                    except:
                        pass
        except Exception as e:
            result['_error'] = str(e)
        return result
    
    # Handle dict-like objects
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            try:
                # Convert bytes keys to strings
                if isinstance(key, bytes):
                    key_str = try_decode_text(key) or key.hex()[:50]
                else:
                    key_str = str(key)
                result[key_str] = deep_extract_value(value, max_depth, current_depth + 1)
            except Exception as e:
                result[str(key)] = f"<error extracting: {e}>"
        return result
    
    # Handle list-like objects
    if isinstance(obj, (list, tuple)):
        return [deep_extract_value(item, max_depth, current_depth + 1) for item in obj]
    
    # Try to extract attributes from objects
    if hasattr(obj, '__dict__'):
        result = {'_type': type(obj).__name__}
        try:
            for attr_name in dir(obj):
                if attr_name.startswith('_'):
                    continue
                try:
                    attr_value = getattr(obj, attr_name)
                    if not callable(attr_value):
                        result[attr_name] = deep_extract_value(attr_value, max_depth, current_depth + 1)
                except:
                    pass
            return result
        except:
            pass
    
    # Fallback to string representation
    return str(obj)


def extract_psd_data(psd_path: Path) -> Dict[str, Any]:
    """Extract all data from a PSD file."""
    print(f"Reading PSD file: {psd_path.name}...")
    
    try:
        psd = PSDImage.open(psd_path)
    except Exception as e:
        return {'error': f"Failed to open PSD: {e}"}
    
    data = {
        'header': {
            'width': psd.width,
            'height': psd.height,
            'depth': psd.depth,
            'channels': psd.channels,
            'color_mode': str(psd.color_mode),
            'version': psd.version if hasattr(psd, 'version') else None,
        },
        'layers': [],
    }
    
    # Extract all layers
    if hasattr(psd, 'layers'):
        for layer in psd.layers:
            data['layers'].append(extract_layer_info(layer))
    
    # Extract image resources
    if hasattr(psd, 'image_resources'):
        resources = {}
        for key, value in psd.image_resources.items():
            try:
                # Try to get actual data from ImageResource object
                if hasattr(value, 'data'):
                    resource_data = value.data
                    if isinstance(resource_data, bytes):
                        decoded_text = try_decode_text(resource_data)
                        resource_info = {
                            'type': 'bytes',
                            'size': len(resource_data),
                            'hex_preview': resource_data.hex()[:500] if len(resource_data) > 0 else '',
                            'full_hex': resource_data.hex()  # Full hex for comparison
                        }
                        if decoded_text:
                            resource_info['decoded_text'] = decoded_text[:1000]  # First 1000 chars
                        resources[str(key)] = resource_info
                    elif isinstance(resource_data, dict):
                        # Deep extract from dict (handles Enumerated objects)
                        resources[str(key)] = deep_extract_value(resource_data)
                    else:
                        # Deep extract from other types
                        resources[str(key)] = deep_extract_value(resource_data)
                elif isinstance(value, bytes):
                    decoded_text = try_decode_text(value)
                    resource_info = {
                        'type': 'bytes',
                        'size': len(value),
                        'hex_preview': value.hex()[:500] if len(value) > 0 else '',
                        'full_hex': value.hex()
                    }
                    if decoded_text:
                        resource_info['decoded_text'] = decoded_text[:1000]
                    resources[str(key)] = resource_info
                elif isinstance(value, dict):
                    # Deep extract from dict
                    resources[str(key)] = deep_extract_value(value)
                else:
                    # Deep extract from object
                    resources[str(key)] = deep_extract_value(value)
            except Exception as e:
                resources[str(key)] = {'error': str(e), 'type': type(value).__name__ if hasattr(value, '__class__') else 'unknown'}
        if resources:
            data['image_resources'] = resources
    
    # Extract tagged blocks (metadata)
    if hasattr(psd, 'tagged_blocks'):
        tagged_blocks = {}
        for key, value in psd.tagged_blocks.items():
            try:
                # Try to get actual data from TaggedBlock object
                if hasattr(value, 'data'):
                    block_data = value.data
                    if isinstance(block_data, bytes):
                        decoded_text = try_decode_text(block_data)
                        tagged_blocks[str(key)] = {
                            'type': 'bytes',
                            'size': len(block_data),
                            'hex_preview': block_data.hex()[:500] if len(block_data) > 0 else '',
                            'full_hex': block_data.hex()  # Full hex for comparison
                        }
                        if decoded_text:
                            tagged_blocks[str(key)]['decoded_text'] = decoded_text[:1000]
                    elif isinstance(block_data, dict):
                        # Deep extract from dict (handles Enumerated objects)
                        tagged_blocks[str(key)] = deep_extract_value(block_data)
                    else:
                        # Deep extract from other types
                        tagged_blocks[str(key)] = deep_extract_value(block_data)
                elif isinstance(value, bytes):
                    decoded_text = try_decode_text(value)
                    tagged_blocks[str(key)] = {
                        'type': 'bytes',
                        'size': len(value),
                        'hex_preview': value.hex()[:500] if len(value) > 0 else '',
                        'full_hex': value.hex()
                    }
                    if decoded_text:
                        tagged_blocks[str(key)]['decoded_text'] = decoded_text[:1000]
                elif isinstance(value, dict):
                    # Deep extract from dict
                    tagged_blocks[str(key)] = deep_extract_value(value)
                else:
                    # Deep extract from object
                    tagged_blocks[str(key)] = deep_extract_value(value)
            except Exception as e:
                tagged_blocks[str(key)] = {'error': str(e), 'type': type(value).__name__ if hasattr(value, '__class__') else 'unknown'}
        if tagged_blocks:
            data['tagged_blocks'] = tagged_blocks
    
    # Extract color mode data
    if hasattr(psd, 'color_mode_data'):
        try:
            if isinstance(psd.color_mode_data, bytes):
                data['color_mode_data'] = {
                    'type': 'bytes',
                    'size': len(psd.color_mode_data),
                    'preview': psd.color_mode_data.hex()[:200]
                }
            else:
                data['color_mode_data'] = str(psd.color_mode_data)
        except:
            data['color_mode_data'] = "<unavailable>"
    
    return data


def compare_dicts(dict1: Dict, dict2: Dict, path: str = "") -> List[Tuple[str, Any, Any]]:
    """Compare two dictionaries and return list of differences."""
    differences = []
    
    # Get all keys from both dicts
    all_keys = set(dict1.keys()) | set(dict2.keys())
    
    for key in all_keys:
        current_path = f"{path}.{key}" if path else key
        
        if key not in dict1:
            differences.append((current_path, "MISSING", dict2[key]))
        elif key not in dict2:
            differences.append((current_path, dict1[key], "MISSING"))
        elif isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
            # Special handling for dicts with 'full_hex' keys (byte data)
            if 'full_hex' in dict1[key] and 'full_hex' in dict2[key]:
                # Compare hex strings directly
                if dict1[key]['full_hex'] != dict2[key]['full_hex']:
                    # If we have decoded text, show that instead of hex
                    if 'decoded_text' in dict1[key] or 'decoded_text' in dict2[key]:
                        text1 = dict1[key].get('decoded_text', 'N/A')
                        text2 = dict2[key].get('decoded_text', 'N/A')
                        differences.append((current_path, 
                                          f"Text: {text1[:200]}",
                                          f"Text: {text2[:200]}"))
                    else:
                        differences.append((current_path, 
                                          f"Hex length: {len(dict1[key]['full_hex'])}, preview: {dict1[key].get('hex_preview', '')[:100]}",
                                          f"Hex length: {len(dict2[key]['full_hex'])}, preview: {dict2[key].get('hex_preview', '')[:100]}"))
            else:
                # Recursively compare nested dicts
                differences.extend(compare_dicts(dict1[key], dict2[key], current_path))
        elif isinstance(dict1[key], list) and isinstance(dict2[key], list):
            # Compare lists
            if len(dict1[key]) != len(dict2[key]):
                differences.append((current_path, f"List length {len(dict1[key])}", f"List length {len(dict2[key])}"))
            else:
                for i, (item1, item2) in enumerate(zip(dict1[key], dict2[key])):
                    if isinstance(item1, dict) and isinstance(item2, dict):
                        differences.extend(compare_dicts(item1, item2, f"{current_path}[{i}]"))
                    elif item1 != item2:
                        differences.append((f"{current_path}[{i}]", item1, item2))
        elif dict1[key] != dict2[key]:
            differences.append((current_path, dict1[key], dict2[key]))
    
    return differences


def format_difference(path: str, value1: Any, value2: Any) -> str:
    """Format a difference for display."""
    # Truncate long values
    def truncate(val, max_len=200):
        s = str(val)
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s
    
    v1_str = truncate(value1)
    v2_str = truncate(value2)
    
    # If values are hex strings, show first and last parts
    if isinstance(value1, str) and isinstance(value2, str):
        if len(value1) > 100 or len(value2) > 100:
            if 'Hex length' in value1:
                return f"  {path}:\n    File 1: {value1}\n    File 2: {value2}"
    
    return f"  {path}:\n    File 1: {v1_str}\n    File 2: {v2_str}"


def main():
    """Main comparison function."""
    script_dir = Path(__file__).parent
    file1_path = script_dir / "texturetemplate2.psd"
    file2_path = script_dir / "texturetemplate3.psd"
    
    # Check if files exist
    if not file1_path.exists():
        print(f"ERROR: File not found: {file1_path}")
        return
    
    if not file2_path.exists():
        print(f"ERROR: File not found: {file2_path}")
        return
    
    print("=" * 80)
    print("PSD File Comparison Tool")
    print("=" * 80)
    print(f"\nComparing:")
    print(f"  File 1: {file1_path.name}")
    print(f"  File 2: {file2_path.name}\n")
    
    # Extract data from both files
    data1 = extract_psd_data(file1_path)
    data2 = extract_psd_data(file2_path)
    
    # Check for errors
    if 'error' in data1:
        print(f"ERROR: {data1['error']}")
        return
    
    if 'error' in data2:
        print(f"ERROR: {data2['error']}")
        return
    
    print("\n" + "=" * 80)
    print("COMPARISON RESULTS")
    print("=" * 80)
    
    # Compare the data
    differences = compare_dicts(data1, data2)
    
    if not differences:
        print("\n✅ No differences found! The files appear to be identical.")
        return
    
    print(f"\n❌ Found {len(differences)} difference(s):\n")
    
    # Group differences by category
    layer_diffs = []
    metadata_diffs = []
    resource_diffs = []
    header_diffs = []
    other_diffs = []
    
    for path, val1, val2 in differences:
        if path.startswith('layers'):
            layer_diffs.append((path, val1, val2))
        elif path.startswith('image_resources') or path.startswith('tagged_blocks'):
            metadata_diffs.append((path, val1, val2))
        elif path.startswith('header'):
            header_diffs.append((path, val1, val2))
        else:
            other_diffs.append((path, val1, val2))
    
    # Print differences by category
    if header_diffs:
        print("\n" + "-" * 80)
        print("HEADER DIFFERENCES:")
        print("-" * 80)
        for path, val1, val2 in header_diffs:
            print(format_difference(path, val1, val2))
    
    if layer_diffs:
        print("\n" + "-" * 80)
        print("LAYER DIFFERENCES:")
        print("-" * 80)
        for path, val1, val2 in layer_diffs:
            print(format_difference(path, val1, val2))
    
    if metadata_diffs:
        print("\n" + "-" * 80)
        print("METADATA / RESOURCE DIFFERENCES (Most likely addon settings):")
        print("-" * 80)
        for path, val1, val2 in metadata_diffs:
            print(format_difference(path, val1, val2))
    
    if other_diffs:
        print("\n" + "-" * 80)
        print("OTHER DIFFERENCES:")
        print("-" * 80)
        for path, val1, val2 in other_diffs:
            print(format_difference(path, val1, val2))
    
    # Save detailed comparison to JSON
    output_file = script_dir / "psd_comparison_report.json"
    report = {
        'file1': str(file1_path.name),
        'file2': str(file2_path.name),
        'total_differences': len(differences),
        'differences': [
            {
                'path': path,
                'file1_value': str(val1),
                'file2_value': str(val2)
            }
            for path, val1, val2 in differences
        ],
        'full_data1': data1,
        'full_data2': data2
    }
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n📄 Detailed report saved to: {output_file.name}")
    except Exception as e:
        print(f"\n⚠️  Could not save JSON report: {e}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

