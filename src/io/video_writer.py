import cv2

class VideoWriter:
    def __init__(self, output_path, frame_width, frame_height, fps=30):
        self.output_path = output_path
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.fps = fps
        self.fourcc = cv2.VideoWriter_fourcc(*'XVID')
        self.writer = cv2.VideoWriter(self.output_path, self.fourcc, self.fps, (self.frame_width, self.frame_height))

    def write_frame(self, frame):
        if self.writer is not None:
            self.writer.write(frame)

    def release(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None