def get_color_map(value, color_ranges):
    for range in color_ranges:
        if range['min'] <= value <= range['max']:
            return range['color']
    return (0, 0, 0)  # Default to black if no range matches

def load_color_ranges(file_path):
    import yaml
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def apply_color_map_to_values(values, color_ranges):
    return [get_color_map(value, color_ranges) for value in values]