"""
vxPy_app ./visuals/spherical_grating/spherical_grating.py
Copyright (C) 2022 Tim Hladnik

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
from vispy import gloo
from vispy.util import transforms
import numpy as np

from vxpy.core import visual
from vxpy.utils import sphere


class MotionAxis(visual.Mat4Parameter):
    def __init__(self, *args, **kwargs):
        visual.Mat4Parameter.__init__(self, *args, **kwargs)

        self.value_map = {'forward': self._rotate_forward,
                          'sideways': self._rotate_sideways,
                          'vertical': np.eye(4)}

    @staticmethod
    def _rotate_forward():
        return transforms.rotate(90, (0, 1, 0))

    @staticmethod
    def _rotate_sideways():
        return transforms.rotate(90, (1, 0, 0))


class SingleDotRotatingAroundAxis(visual.SphericalVisual):

    # Define parameters
    time = visual.FloatParameter('time', internal=True)
    motion_axis = MotionAxis('motion_axis', static=True)
    dot_polarity = visual.IntParameter('dot_polarity', value_map={'dark-on-light': 1, 'light-on-dark': 2}, static=True)
    dot_start_angle = visual.FloatParameter('dot_start_angle', default=0, limits=(-180, 180), step_size=5, static=True)
    dot_angular_velocity = visual.FloatParameter('dot_angular_velocity', default=60, limits=(-360, 360), step_size=5, static=True)
    dot_angular_diameter = visual.FloatParameter('dot_angular_diameter', default=10, limits=(1, 90), step_size=1, static=True)
    dot_offset_angle = visual.FloatParameter('dot_offset_angle', default=0, limits=(-85, 85), step_size=5, static=True)

    # Paths to shaders
    VERT_PATH = './single_dot_around_axis.vert'
    FRAG_PATH = './single_dot_around_axis.frag'

    def __init__(self, *args, **kwargs):
        visual.SphericalVisual.__init__(self, *args, **kwargs)

        # Set up 3d model of sphere
        self.sphere = sphere.UVSphere(azim_lvls=60, elev_lvls=30, upper_elev=np.pi/2)
        self.index_buffer = gloo.IndexBuffer(self.sphere.indices)
        self.position_buffer = gloo.VertexBuffer(self.sphere.a_position)
        self.azimuth_buffer = gloo.VertexBuffer(self.sphere.a_azimuth)
        self.elevation_buffer = gloo.VertexBuffer(self.sphere.a_elevation)

        # Set up program
        self.rotating_dot = gloo.Program(self.load_vertex_shader(self.VERT_PATH), self.load_shader(self.FRAG_PATH))

        # Connect parameters (this makes them be automatically updated in the connected programs)
        self.time.connect(self.rotating_dot)
        self.motion_axis.connect(self.rotating_dot)
        self.dot_polarity.connect(self.rotating_dot)
        self.dot_start_angle.connect(self.rotating_dot)
        self.dot_angular_velocity.connect(self.rotating_dot)
        self.dot_angular_diameter.connect(self.rotating_dot)
        self.dot_offset_angle.connect(self.rotating_dot)

        # Add reset trigger
        self.trigger_functions.append(self.reset_time)

    def reset_time(self):
        self.time.data = 0.0

    def initialize(self, **params):
        # Reset u_time to 0 on each visual initialization
        self.reset_time()

        # Set positions with buffers
        self.rotating_dot['a_position'] = self.position_buffer
        self.rotating_dot['a_azimuth'] = self.azimuth_buffer
        self.rotating_dot['a_elevation'] = self.elevation_buffer

    def render(self, dt):
        # Add elapsed time to u_time
        self.time.data += dt

        # Apply default transforms to the program for mapping according to hardware calibration
        self.apply_transform(self.rotating_dot)

        # Draw the actual visual stimulus using the indices of the  triangular faces
        self.rotating_dot.draw('triangles', self.index_buffer)
