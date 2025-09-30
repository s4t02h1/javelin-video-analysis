<<<<<<< HEAD
# Javelin Video Analysis

This project implements a video analysis program focused on javelin performance. It includes features for speed visualization, acceleration heatmaps, and javelin tip tracking using various tracking algorithms.

## Project Structure

```
javelin-video-analysis
├── src
│   ├── app.py                     # Main entry point for the application
│   ├── pipelines
│   │   ├── speed_visualization.py  # Functions for visualizing speed with color ranges
│   │   ├── acceleration_heatmap.py # Calculates and visualizes acceleration heatmap
│   │   └── tip_tracking.py         # Implements javelin tip tracking
│   ├── tracking
│   │   ├── marker_based.py         # Marker-based tracking functions
│   │   └── object_tracking.py      # Object tracking algorithms
│   ├── io
│   │   ├── video_reader.py         # Functionality to read video files
│   │   └── video_writer.py         # Handles writing processed video files
│   ├── utils
│   │   ├── geometry.py             # Utility functions for geometric calculations
│   │   ├── filters.py              # Functions for applying data filters
│   │   ├── color_maps.py           # Color mapping functions for visualization
│   │   └── visualization.py         # Functions for rendering visualizations
│   └── types
│       └── __init__.py             # Custom types and data structures
├── configs
│   ├── default.yaml                # Default settings for the application
│   ├── color_ranges.yaml           # Fixed color ranges for speed visualization
│   └── tracking.yaml               # Settings for tracking algorithms
├── data
│   ├── input                       # Directory for input video files
│   └── output                      # Directory for output video files and results
├── tests
│   ├── test_tip_tracking.py        # Unit tests for tip tracking functionality
│   ├── test_speed_visualization.py  # Unit tests for speed visualization
│   └── test_acceleration_heatmap.py # Unit tests for acceleration heatmap
├── scripts
│   ├── run_pipeline.py             # Script to run the video analysis pipeline
│   └── export_metrics.py           # Script to export analysis metrics
├── requirements.txt                # Project dependencies
├── pyproject.toml                  # Project configuration
└── README.md                       # Project documentation
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd javelin-video-analysis
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

To run the video analysis pipeline, execute the following command:
```
python src/scripts/run_pipeline.py
```

Make sure to place your input video files in the `data/input` directory. The output will be saved in the `data/output` directory.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
=======
# javelin-video-analysis
analysing javelin throw technique
>>>>>>> origin/main
