def calculate_distance(point1, point2):
    """Calculate the Euclidean distance between two points."""
    return ((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2) ** 0.5

def midpoint(point1, point2):
    """Calculate the midpoint between two points."""
    return ((point1[0] + point2[0]) / 2, (point1[1] + point2[1]) / 2)

def angle_between_points(point1, point2):
    """Calculate the angle in degrees between two points."""
    import math
    delta_y = point2[1] - point1[1]
    delta_x = point2[0] - point1[0]
    return math.degrees(math.atan2(delta_y, delta_x))

def is_point_within_bounds(point, bounds):
    """Check if a point is within given bounds."""
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]