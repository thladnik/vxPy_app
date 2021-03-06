from typing import Tuple

import cv2
import numpy as np
import pyqtgraph as pg
from PySide6 import QtWidgets, QtGui, QtCore

from vxpy import config
from vxpy.api.ui import register_with_plotter
from vxpy.api.attribute import write_to_file
import vxpy.core.attribute as vxattribute
import vxpy.core.gui as vxgui
import vxpy.core.ipc as vxipc
import vxpy.core.routine as vxroutine
from vxpy.definitions import *
from vxpy.utils import widgets


class RoiView(pg.GraphicsLayoutWidget):
    def __init__(self, parent, **kwargs):
        pg.GraphicsLayoutWidget.__init__(self, parent=parent, **kwargs)

        self.setFixedHeight(120)

        # Set up plot image item
        self.image_plot = self.addPlot(0, 0, 1, 10)
        self.image_item = pg.ImageItem()
        self.image_plot.hideAxis('left')
        self.image_plot.hideAxis('bottom')
        self.image_plot.setAspectLocked(True)
        self.image_plot.invertY(True)
        self.image_plot.addItem(self.image_item)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_image)
        self.timer.setInterval(50)
        self.timer.start()

    def _update_image(self):
        # Read last frame
        idx, time, frame = vxattribute.read_attribute('particle_rois')

        if idx[0] is None:
            return

        # Set frame data on image plot
        self.image_item.setImage(np.vstack(frame[0]))


class Roi(pg.RectROI):
    def __init__(self):
        pg.RectROI.__init__(self, FreeswimTrackerRoutine.calibration_rect_pos,
                            [100, 100], sideScalers=True,
                            pen=pg.mkPen(color='orange', width=2),
                            maxBounds=QtCore.QRectF(0, 0, 1924, 1080))

        self.active_calibration = False

    def set_calibration_mode(self, active):

        self.active_calibration = active
        self.translatable = self.active_calibration
        self.resizable = self.active_calibration

        self.update_handles()

    def update_handles(self):
        for h in self.handles:
            if self.active_calibration:
                h['item'].show()
            else:
                h['item'].hide()

    # def mouseDragEvent(self, ev):
    #     self.update_handles()
    #     ev.accept()


class FrameView(pg.GraphicsLayoutWidget):
    def __init__(self, parent, **kwargs):
        pg.GraphicsLayoutWidget.__init__(self, parent=parent, **kwargs)

        self._calibrate = False
        self._points = []
        self._attribute = None

        # Set up plot image item
        self.image_plot = self.addPlot(0, 0, 1, 10)
        self.image_item = pg.ImageItem()
        self.image_plot.hideAxis('left')
        self.image_plot.hideAxis('bottom')
        self.image_plot.setAspectLocked(True)
        self.image_plot.invertY(True)
        self.image_plot.addItem(self.image_item)

        # Add calibration ROI
        self.rect_roi = Roi()
        self.image_plot.vb.addItem(self.rect_roi)

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_image)
        self.timer.setInterval(50)
        self.timer.start()

    def set_attribute(self, frame_name):
        self._attribute = vxattribute.get_attribute(frame_name)

    def _update_image(self):
        if self._attribute is None:
            return

        # Read last frame
        idx, time, frame = self._attribute.read()

        if idx[0] is None:
            return

        # Set frame data on image plot
        self.image_item.setImage(frame[0])


class FreeswimTrackerWidget(vxgui.CameraAddonWidget):
    display_name = 'FreeswimTracker'

    def __init__(self, *args, **kwargs):
        vxgui.AddonWidget.__init__(self, *args, **kwargs)
        self.setLayout(QtWidgets.QHBoxLayout())

        # Add plots
        self.plots = QtWidgets.QWidget(self)
        self.plots.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(self.plots)
        # Frame
        self.frame_view = FrameView(self)
        self.frame_view.rect_roi.sigRegionChangeFinished.connect(self._update_roi_parameters)
        self.plots.layout().addWidget(self.frame_view)

        # ROIs
        self.roi_view = RoiView(self)
        self.plots.layout().addWidget(self.roi_view)
        # Add paraemters

        # Add parameter console
        self.console = QtWidgets.QWidget(self)
        self.console.setLayout(QtWidgets.QVBoxLayout())
        self.console.setMaximumWidth(300)
        self.layout().addWidget(self.console)
        # Display choice
        self.display_choice = widgets.ComboBox(self)
        self.display_choice.connect_callback(self.frame_view.set_attribute)
        self.display_choice.add_items(['freeswim_tracked_zf_frame',
                                       'freeswim_tracked_zf_filtered',
                                       'freeswim_tracked_zf_binary'])
        self.console.layout().addWidget(self.display_choice)
        # Calibration mode
        self.calibration = widgets.ComboBox(self)
        self.calibration.connect_callback(self.set_calibration_mode)
        self.calibration.add_items(['Open', 'Locked'])
        self.console.layout().addWidget(self.calibration)
        # Threshold
        self.binary_threshold = widgets.IntSliderWidget(self.console, label='Threshold [au]',
                                                        default=FreeswimTrackerRoutine.binary_thresh_val,
                                                        limits=(1, 254))
        self.binary_threshold.connect_callback(self.set_binary_threshold)
        self.console.layout().addWidget(self.binary_threshold)
        # Filter size
        self.filter_size = widgets.IntSliderWidget(self.console, label='Filter size [au]',
                                                   default=FreeswimTrackerRoutine.filter_size,
                                                   limits=(1, 255))
        self.filter_size.connect_callback(self.set_filter_size)
        self.console.layout().addWidget(self.filter_size)
        # Min area
        self.min_area = widgets.IntSliderWidget(self.console, label='Min. area [au]',
                                                default=FreeswimTrackerRoutine.min_area,
                                                limits=(1, 255))
        self.min_area.connect_callback(self.set_min_area)
        self.console.layout().addWidget(self.min_area)
        # X dim
        self.x_dimension_length = widgets.IntSliderWidget(self.console, label='X dimension [mm]',
                                                          default=FreeswimTrackerRoutine.dimension_size[0],
                                                          limits=(1, 1000))
        self.x_dimension_length.connect_callback(self.set_x_dimension_size)
        self.console.layout().addWidget(self.x_dimension_length)
        # Y dim
        self.y_dimension_length = widgets.IntSliderWidget(self.console, label='Y dimension [mm]',
                                                          default=FreeswimTrackerRoutine.dimension_size[1],
                                                          limits=(1, 1000))
        self.y_dimension_length.connect_callback(self.set_y_dimension_size)
        self.console.layout().addWidget(self.y_dimension_length)
        # Spacer
        self.console.layout().addItem(QtWidgets.QSpacerItem(1, 1,
                                                            QtWidgets.QSizePolicy.Minimum,
                                                            QtWidgets.QSizePolicy.MinimumExpanding))

    def set_calibration_mode(self, mode):
        self.frame_view.rect_roi.set_calibration_mode(mode == 'Open')

    def set_filter_size(self):
        self.call_routine(FreeswimTrackerRoutine.set_filter_size, self.filter_size.get_value())

    def set_min_area(self):
        self.call_routine(FreeswimTrackerRoutine.set_min_area, self.min_area.get_value())

    def set_binary_threshold(self, value):
        vxipc.rpc(PROCESS_CAMERA, FreeswimTrackerRoutine.set_binary_threshold, value)
        # self.call_routine(FreeswimTrackerRoutine.set_binary_threshold, self.binary_threshold.get_value())

    def set_x_dimension_size(self):
        self.call_routine(FreeswimTrackerRoutine.set_x_dimension_size, self.x_dimension_length.get_value())

    def set_y_dimension_size(self):
        self.call_routine(FreeswimTrackerRoutine.set_y_dimension_size, self.y_dimension_length.get_value())

    def _update_roi_parameters(self):
        pos = self.frame_view.rect_roi.pos()
        self.call_routine(FreeswimTrackerRoutine.set_calibration_rect_pos, (pos.x(), pos.y()))
        size = self.frame_view.rect_roi.size()
        self.call_routine(FreeswimTrackerRoutine.set_calibration_rect_size, (size.x(), size.y()))


class FreeswimTrackerRoutine(vxroutine.CameraRoutine):
    rect_size = (60, 60)
    camera_device_id = 'multiple_fish_vertical_swim'

    # Set processing parameters
    dimension_size = np.array([100., 80.])  # mm
    binary_thresh_val = 25
    min_area = 10
    filter_size = 31
    calibration_rect_pos = np.array([0, 0])
    calibration_rect_size = np.array([1, 1])
    max_particle_number = 10

    def setup(self):

        # Get camera properties
        camera_config = config.CONF_CAMERA_DEVICES.get(self.camera_device_id)
        self.res_x = camera_config['width']
        self.res_y = camera_config['height']

        self.freeswim_tracked_zf_frame = vxattribute.ArrayAttribute('freeswim_tracked_zf_frame',
                                                                    (self.res_x, self.res_y, 3),
                                                                    vxattribute.ArrayType.uint8)
        self.freeswim_tracked_zf_filtered = vxattribute.ArrayAttribute('freeswim_tracked_zf_filtered',
                                                                       (self.res_x, self.res_y),
                                                                       vxattribute.ArrayType.uint8)
        self.freeswim_tracked_zf_binary = vxattribute.ArrayAttribute('freeswim_tracked_zf_binary',
                                                                     (self.res_x, self.res_y),
                                                                     vxattribute.ArrayType.uint8)
        self.particle_rois = vxattribute.ArrayAttribute('particle_rois',
                                                        (self.max_particle_number, *self.rect_size),
                                                        dtype=vxattribute.ArrayType.uint8,
                                                        chunked=True)

        self.particle_count_total = vxattribute.ArrayAttribute('particle_count_total',
                                                               (1,),
                                                               dtype=vxattribute.ArrayType.uint64)
        self.particle_count_filtered = vxattribute.ArrayAttribute('particle_count_filtered',
                                                                  (1,),
                                                                  dtype=vxattribute.ArrayType.uint64)
        self.particle_mapped_position = vxattribute.ArrayAttribute('particle_mapped_position',
                                                                   (self.max_particle_number, 2,),
                                                                   dtype=vxattribute.ArrayType.float64)

    def initialize(self):
        # Create mixture of gaussian BG subtractor
        self.mog = cv2.createBackgroundSubtractorMOG2(400, detectShadows=False)

        # Add expposed methods
        self.exposed.append(FreeswimTrackerRoutine.set_calibration_rect_pos)
        self.exposed.append(FreeswimTrackerRoutine.set_calibration_rect_size)
        self.exposed.append(FreeswimTrackerRoutine.set_x_dimension_size)
        self.exposed.append(FreeswimTrackerRoutine.set_y_dimension_size)
        self.exposed.append(FreeswimTrackerRoutine.set_min_area)
        self.exposed.append(FreeswimTrackerRoutine.set_binary_threshold)
        self.exposed.append(FreeswimTrackerRoutine.set_filter_size)

        register_with_plotter('particle_count_total', axis='particle_count')
        register_with_plotter('particle_count_filtered', axis='particle_count')

        write_to_file(self, 'particle_rois')
        write_to_file(self, 'particle_count_total')
        write_to_file(self, 'particle_count_filtered')
        write_to_file(self, 'particle_mapped_position')

    def set_calibration_rect_pos(self, value):
        self.calibration_rect_pos = np.array(value)

    def set_calibration_rect_size(self, value):
        self.calibration_rect_size = np.array(value)

    def set_x_dimension_size(self, value):
        self.dimension_size[0] = value

    def set_y_dimension_size(self, value):
        self.dimension_size[1] = value

    def set_min_area(self, value):
        self.min_area = value

    def set_binary_threshold(self, value):
        self.binary_thresh_val = value

    def set_filter_size(self, value):
        self.filter_size = value // 2 * 2 + 1  # always make sure that filter size is odd integer

    def _apply_dimensions(self, point: np.ndarray) -> np.ndarray:
        p = point.copy()
        p = p - self.calibration_rect_pos
        p = p / self.calibration_rect_size
        p = p * self.dimension_size
        p[1] = self.dimension_size[1] - p[1]

        return p

    def main(self, **frames):
        frame = frames.get(self.camera_device_id)

        if frame is None:
            return

        if frame.ndim > 2:
            frame = frame[:, :, 0].T
        frame = frame.T

        display_frame = np.repeat(frame[:, :, np.newaxis], 3, axis=-1)
        display_frame = cv2.rotate(cv2.flip(display_frame, 0), cv2.ROTATE_90_CLOCKWISE)

        # Calculate background distribution and foreground mask
        foreground_mask = self.mog.apply(frame)

        # Smooth mask
        filtered_frame = cv2.GaussianBlur(foreground_mask, (self.filter_size,) * 2, cv2.BORDER_DEFAULT)
        self.freeswim_tracked_zf_filtered.write(filtered_frame)

        # Apply threshold
        _, thresh_frame = cv2.threshold(filtered_frame, self.binary_thresh_val, 255, cv2.THRESH_BINARY)
        self.freeswim_tracked_zf_binary.write(thresh_frame)

        # Detect and filter contours
        contours, hierarchy = cv2.findContours(thresh_frame, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        xdiff, ydiff = self.rect_size[0] // 2, self.rect_size[1] // 2
        particle_rectangles = []
        particle_areas = []
        particle_positions = []
        # print('---')
        # print('Pos', self.calibration_rect_pos)
        # print('Size', self.calibration_rect_size)
        self.particle_count_total.write(len(contours))
        if len(contours) > 0:
            i = 0
            for cnt in contours:

                M = cv2.moments(cnt)
                area = cv2.contourArea(cnt)
                if area < self.min_area:
                    continue

                # Calculate centroid
                centroid = np.array([int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])])
                c_rev = np.array([centroid[1], centroid[0]])
                mapped_position = self._apply_dimensions(c_rev)

                # Crop rectangular ROI
                rect = frame[centroid[1] - ydiff:centroid[1] + ydiff, centroid[0] - xdiff:centroid[0] + xdiff]

                # Mark ROIs on display frame
                cv2.rectangle(display_frame,
                              [c_rev[0] - xdiff, c_rev[1] - ydiff], [c_rev[0] + xdiff, c_rev[1] + ydiff],
                              (255, 0, 0), 2)

                text_args = (cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                cv2.putText(display_frame,
                            f'x: {mapped_position[0]:.1f}',
                            (c_rev[0] + xdiff + 5, c_rev[1] - ydiff // 2), *text_args)
                cv2.putText(display_frame,
                            f'y: {mapped_position[1]:.1f}',
                            (c_rev[0] + xdiff + 5, c_rev[1] - ydiff // 2 + 25), *text_args)

                if rect.shape == self.rect_size:
                    particle_rectangles.append(rect)
                    particle_areas.append((area, i))
                    particle_positions.append(mapped_position)
                    i += 1

        self.particle_count_filtered.write(len(particle_areas))

        if len(particle_areas) > 0:
            # Sort particles by size
            particle_areas = sorted(particle_areas)[::-1]
            if len(particle_areas) > 10:
                particle_areas = particle_areas[:10]

            # Write particle ROIs to attribute
            new_rects = np.zeros(self.particle_rois.shape)
            new_positions = -np.ones(self.particle_mapped_position.shape)
            for k, (_, i) in enumerate(particle_areas):
                new_rects[k] = particle_rectangles[i]
                new_positions[k] = particle_positions[i]

            # Write particle boxes
            self.particle_rois.write(new_rects)

            # Write centroid positions
            # print(new_positions)
            self.particle_mapped_position.write(new_positions)

        display_frame = cv2.flip(cv2.rotate(display_frame, cv2.ROTATE_90_COUNTERCLOCKWISE), 0)
        self.freeswim_tracked_zf_frame.write(display_frame)
