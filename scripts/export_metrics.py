import json
import os

def export_metrics(metrics, output_path):
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    metrics_file = os.path.join(output_path, 'metrics.json')
    
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=4)

if __name__ == "__main__":
    # Example metrics to export
    example_metrics = {
        "speed": [5.2, 6.1, 7.3],
        "acceleration": [0.5, 0.7, 0.9],
        "tracking": {
            "javelin_tip": {
                "x": [100, 150, 200],
                "y": [200, 250, 300]
            }
        }
    }
    
    output_directory = "../data/output"
    export_metrics(example_metrics, output_directory)