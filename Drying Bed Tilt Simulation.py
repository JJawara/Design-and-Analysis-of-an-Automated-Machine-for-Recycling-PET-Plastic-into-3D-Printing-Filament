import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import pymunk
import numpy as np
import random
import time

# ---------------- Constants ----------------
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 700
BED_CENTER_2D = (0, 0)
BED_R = 9.0
N_PELLETS = 500
PELLET_R = 0.2
LIFT_HEIGHT = 1.5
FORCE_FACTOR = 100.0    # Force multiplier for tilt
DAMPING = 10000         # High damping for rolling resistance
LIGHT_POSITION = [0, 20, 0, 1]

# --- Animation Parameters (LOCKED) ---
FLATTEN_WALL_LIFT_DUR = 1.5 
FLATTEN_RAM_HOLD_DUR = 2.0  
FLATTEN_RAM_IMPULSE = 3.5   
SCRAMBLE_THUMP_DUR = 0.15    
SCRAMBLE_PAUSE = 5.0        
SCRAMBLE_IMPULSE = 3.0      
DUMP_HOLD_DUR = 0.8
DUMP_IMPULSE = 2.5  

ACTUATOR_ANGLES_DEG = np.array([90, 210, 330])
ACTUATOR_ANGLES_RAD = np.deg2rad(ACTUATOR_ANGLES_DEG)

# ---------------- Physics and Pellet Management ----------------
def get_initial_pellets(n, mode='random'):
    pellets = []
    if mode == 'mountain':
        for _ in range(n):
            r = np.sqrt(random.random()) * (BED_R * 0.3)
            a = random.uniform(0, 2 * np.pi)
            pos = (BED_CENTER_2D[0] + r * np.cos(a), BED_CENTER_2D[1] + r * np.sin(a))
            pellets.append(pos)
    else:
        for _ in range(n):
            r = np.sqrt(random.random()) * (BED_R - PELLET_R * 2)
            a = random.uniform(0, 2 * np.pi)
            pos = (BED_CENTER_2D[0] + r * np.cos(a), BED_CENTER_2D[1] + r * np.sin(a))
            pellets.append(pos)
    return pellets

def add_pellet(space, pos):
    body = pymunk.Body(1, 100)
    body.position = pos
    body.linear_damping = DAMPING
    body.angular_damping = DAMPING
    shape = pymunk.Circle(body, PELLET_R)
    shape.elasticity = 0.1
    shape.friction = 1.2
    space.add(body, shape)
    return shape

def setup_space(pellet_positions):
    space = pymunk.Space()
    space.gravity = (0, 0)
    
    static_body = space.static_body
    wall_segments = []
    num_segments = 36
    for i in range(num_segments):
        angle1 = 2 * np.pi * i / num_segments
        angle2 = 2 * np.pi * (i + 1) / num_segments
        p1 = (BED_CENTER_2D[0] + BED_R * np.cos(angle1), BED_CENTER_2D[1] + BED_R * np.sin(angle1))
        p2 = (BED_CENTER_2D[0] + BED_R * np.cos(angle2), BED_CENTER_2D[1] + BED_R * np.sin(angle2))
        segment = pymunk.Segment(static_body, p1, p2, 0.1)
        segment.elasticity = 0.5
        segment.friction = 1.5
        wall_segments.append(segment)
    space.add(*wall_segments)
    pellet_shapes = [add_pellet(space, pos) for pos in pellet_positions]
    return space, pellet_shapes

def get_plane_normal(lifts):
    points = []
    for i, angle in enumerate(ACTUATOR_ANGLES_RAD):
        points.append([BED_R * np.cos(angle), lifts[i], BED_R * np.sin(angle)])
    p1, p2, p3 = np.array(points[0]), np.array(points[1]), np.array(points[2])
    normal = np.cross(p2 - p1, p3 - p1)
    if normal[1] < 0: normal *= -1
    norm_val = np.linalg.norm(normal)
    if norm_val < 1e-6: return np.array([0, 1, 0])
    return normal / norm_val

def apply_forces_to_pellets(space, lifts, impulse):
    """NEW PHYSICS: Applies a force to each pellet based on the bed's tilt."""
    normal = get_plane_normal(lifts)
    # The gravity force is the projection of the 3D 'up' vector onto the 2D plane
    force_vector = (-normal[0], -normal[2])
    
    for body in space.bodies:
        if body.body_type == pymunk.Body.DYNAMIC:
            force = (force_vector[0] * FORCE_FACTOR * impulse, 
                     force_vector[1] * FORCE_FACTOR * impulse)
            body.apply_force_at_local_point(force)

# ---------------- Animation Sequences ----------------
def generate_flatten_sequence():
    seq = []
    num_lift_steps = 10
    for i in range(num_lift_steps):
        lift_amount = (i + 1) / num_lift_steps * LIFT_HEIGHT
        seq.append({'lifts': [0, lift_amount, lift_amount], 'duration': FLATTEN_WALL_LIFT_DUR / num_lift_steps})
    seq.append({'lifts': [LIFT_HEIGHT, 0, 0], 'duration': 0.01, 'impulse': FLATTEN_RAM_IMPULSE})
    seq.append({'lifts': [LIFT_HEIGHT, 0, 0], 'duration': FLATTEN_RAM_HOLD_DUR})
    seq.append({'lifts': [0, 0, 0], 'duration': 2.0})
    return seq

def generate_scramble_sequence():
    seq = []
    thump_lifts = [0, 0, 0]
    random_actuator_idx = random.randint(0, 2)
    thump_lifts[random_actuator_idx] = LIFT_HEIGHT
    seq.append({'lifts': thump_lifts, 'duration': SCRAMBLE_THUMP_DUR, 'impulse': SCRAMBLE_IMPULSE})
    seq.append({'lifts': [0, 0, 0], 'duration': SCRAMBLE_PAUSE})
    return seq

def generate_dump_sequence(cycles=10):
    seq = []
    pushes = [
        {'lifts': [LIFT_HEIGHT, 0, 0], 'duration': DUMP_HOLD_DUR, 'impulse': DUMP_IMPULSE},
        {'lifts': [0, LIFT_HEIGHT, 0], 'duration': DUMP_HOLD_DUR, 'impulse': DUMP_IMPULSE},
        {'lifts': [0, 0, LIFT_HEIGHT], 'duration': DUMP_HOLD_DUR, 'impulse': DUMP_IMPULSE}
    ]
    for _ in range(cycles):
        seq.extend(pushes)
    return seq

# ---------------- Main Application Class ----------------
class ShakerBedSim:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("3D Shaker Bed Simulation (PyOpenGL)")
        self.clock = pygame.time.Clock()
        self.is_paused = False
        self.loop_animation = True
        self.setup_opengl()
        self.reset_simulation()

    def setup_opengl(self):
        glViewport(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        glMatrixMode(GL_PROJECTION)
        gluPerspective(45, (SCREEN_WIDTH / SCREEN_HEIGHT), 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, LIGHT_POSITION)
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.3, 1])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1])
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    def reset_simulation(self, mode='random'):
        self.space, self.pellet_shapes = setup_space(get_initial_pellets(N_PELLETS, mode))
        self.animation_sequence = []
        self.anim_step_idx = -1
        self.anim_step_start_time = 0
        self.is_animating = False
        self.current_animation_name = "IDLE"
        self.lifts = [0, 0, 0]
        self.impulse = 1.0

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_1:
                        self.reset_simulation('mountain')
                        self.animation_sequence = generate_flatten_sequence()
                        self.current_animation_name = "Flattening"
                        self.is_animating = True
                        self.anim_step_idx = -1
                    elif event.key == pygame.K_2:
                        self.reset_simulation()
                        self.animation_sequence = generate_scramble_sequence()
                        self.current_animation_name = "Scrambling"
                        self.is_animating = True
                        self.anim_step_idx = -1
                    elif event.key == pygame.K_3:
                        self.reset_simulation()
                        self.animation_sequence = generate_dump_sequence()
                        self.current_animation_name = "Dumping"
                        self.is_animating = True
                        self.anim_step_idx = -1
                    elif event.key == pygame.K_SPACE:
                        self.is_paused = not self.is_paused
                    elif event.key == pygame.K_l:
                        self.loop_animation = not self.loop_animation
            
            if self.is_animating and not self.is_paused:
                now = time.time()
                if self.anim_step_idx == -1 or (now - self.anim_step_start_time) > self.animation_sequence[self.anim_step_idx]['duration']:
                    self.anim_step_idx += 1
                    if self.anim_step_idx >= len(self.animation_sequence):
                        if self.loop_animation and self.current_animation_name != "Flattening":
                            self.anim_step_idx = 0 
                            if self.current_animation_name == "Scrambling":
                                self.animation_sequence = generate_scramble_sequence()
                        else:
                            self.is_animating = False
                            self.current_animation_name = "IDLE"
                    
                    if self.is_animating:
                        self.anim_step_start_time = now
                        step_data = self.animation_sequence[self.anim_step_idx]
                        self.lifts = step_data['lifts']
                        self.impulse = step_data.get('impulse', 1.0)
            
            if not self.is_animating:
                self.lifts = [0, 0, 0]
                self.impulse = 1.0

            apply_forces_to_pellets(self.space, self.lifts, self.impulse)
            self.space.step(1 / 60.0)

            self.draw_all()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()
        
    def draw_all(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 30, 25, 0, 0, 0, 0, 1, 0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        self.draw_environment()
        glPushMatrix()
        floor_plane = [0, 1, 0, 0.01]
        shadow_matrix = np.zeros(16)
        light_pos_arr = np.array(LIGHT_POSITION)
        d = np.dot(floor_plane, light_pos_arr)
        for i in range(4):
            for j in range(4):
                shadow_matrix[i*4+j] = (d if i==j else 0) - light_pos_arr[i] * floor_plane[j]
        glDisable(GL_LIGHTING)
        glColor4f(0.1, 0.1, 0.1, 0.5)
        glPushMatrix()
        glMultMatrixf(shadow_matrix)
        self.draw_bed_model(is_shadow=True)
        glPopMatrix()
        glEnable(GL_LIGHTING)
        glPopMatrix()
        self.draw_bed_model()
        for pellet in self.pellet_shapes:
            self.draw_pellet(pellet.body.position, self.lifts)
        self.draw_ui()

    def draw_bed_model(self, is_shadow=False):
        glPushMatrix()
        normal = get_plane_normal(self.lifts)
        up = np.array([0, 1, 0])
        axis = np.cross(up, normal)
        angle = np.rad2deg(np.arccos(np.dot(up, normal)))
        if np.linalg.norm(axis) > 1e-6:
            glRotatef(angle, *axis)
        if not is_shadow: glColor3f(0.5, 0.5, 0.55)
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0,1,0)
        glVertex3f(0, 0, 0)
        for i in range(37):
            angle_rad = np.deg2rad(i * 10)
            glVertex3f(BED_R * np.cos(angle_rad), 0, BED_R * np.sin(angle_rad))
        glEnd()
        if not is_shadow: glColor3f(0.8, 0.8, 0.8)
        glBegin(GL_QUAD_STRIP)
        for i in range(37):
            angle_rad = np.deg2rad(i * 10)
            x, z = BED_R * np.cos(angle_rad), BED_R * np.sin(angle_rad)
            glNormal3f(x, 0, z)
            glVertex3f(x, 0, z)
            glVertex3f(x, 0.5, z)
        glEnd()
        glPopMatrix()

    def draw_pellet(self, pos, lifts):
        normal = get_plane_normal(self.lifts)
        if abs(normal[1]) > 1e-6:
             pellet_height = -(normal[0] * pos.x + normal[2] * pos.y) / normal[1]
        else:
             pellet_height = 0
        glPushMatrix()
        glTranslatef(pos.x, pellet_height + PELLET_R, pos.y)
        glColor3f(0.2, 0.6, 0.8)
        quad = gluNewQuadric()
        gluSphere(quad, PELLET_R, 8, 8)
        glPopMatrix()

    def draw_environment(self):
        glColor3f(0.6, 0.6, 0.6)
        glBegin(GL_QUADS)
        glNormal3f(0, 1, 0)
        glVertex3f(-30, 0, -30)
        glVertex3f(-30, 0, 30)
        glVertex3f(30, 0, 30)
        glVertex3f(30, 0, -30)
        glEnd()
        glColor3f(0.5, 0.5, 0.5)
        glBegin(GL_QUADS)
        glNormal3f(0, 0, 1)
        glVertex3f(-30, 0, -30)
        glVertex3f(30, 0, -30)
        glVertex3f(30, 30, -30)
        glVertex3f(-30, 30, -30)
        glEnd()
        
    def draw_ui(self):
        pass

if __name__ == "__main__":
    print("--- 3D Shaker Bed Controls ---")
    print("Press [1] for Flatten Motion (One-Shot)")
    print("Press [2] for Scramble Motion (Loops)")
    print("Press [3] for Dump Motion (Loops)")
    print("Press [SPACE] to Pause/Resume the current animation.")
    print("Press [L] to Toggle Looping for Scramble/Dump.")
    print("----------------------------")
    sim = ShakerBedSim()
    sim.run()