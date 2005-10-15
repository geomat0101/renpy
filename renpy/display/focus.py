# This file contains code to manage focus on the display.

import renpy
import pygame
from pygame.constants import *

class Focus(object):

    def __init__(self, widget, arg, x, y, w, h):
        self.widget = widget
        self.arg = arg
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        
    def __iter__(self):
        return iter((self.widget, self.arg, self.x, self.y, self.w, self.h))

# The widget currently grabbing the input, if any.
grab = None

# Sets the currently focused widget.
def set_focused(widget):
    renpy.game.context().scene_lists.focused = widget

# Gets the currently focused widget.
def get_focused():
    return renpy.game.context().scene_lists.focused

def set_grab(widget):
    global grab
    grab = widget

def get_grab():
    return grab
    
# The current list of focuses that we know about.
focus_list = [ ]

# This takes in a focus list from the rendering system.
def take_focuses(fl):
    global focus_list
    focus_list = fl

# This is called before each interaction. It's purpose is to choose
# the widget that is focused, and to mark it as focused and all of
# the other widgets as unfocused.

def before_interact(root):

    # Clear out an old grab.
    global grab
    grab = None

    # a list of focusable, name tuples.
    fwn = [ ]

    def callback(f, n):
        fwn.append((f, n))

    root.find_focusable(callback, None)

    # Assign a full name to each focusable.

    namecount = { }

    for f, n in fwn:
        serial = namecount.get(n, 0)
        namecount[n] = serial + 1
        
        f.full_focus_name = n, serial

    # If there's something with the same full name as the current widget,
    # it becomes the new current widget.

    current = get_focused()
    if current is not None:
        current_name = current.full_focus_name

        for f, n in fwn:
            if f.full_focus_name == current.full_focus_name:
                current = f
                set_focused(f)
                break
        else:
            current = None

    # Otherwise, focus the default widget, or nothing.
    if current is None:

        for f, n in fwn:
            if f.default:
                current = f
                set_focused(f)
                break
        else:        
            set_focused(None)


    # Finally, mark the current widget as the focused widget, and
    # all other widgets as unfocused.
    for f, n in fwn:
        if f is not current:
            f.unfocus()

    if current:
        current.focus(default=True)

    

# This changes the focus to be the widget contained inside the new
# focus object.
def change_focus(newfocus):

    if grab:
        return

    if newfocus is None:
        widget = None
    else:
        widget = newfocus.widget

    current = get_focused()

    # Nothing to do.
    if current is widget:
        return

    if current is not None:
        current.unfocus()

    current = widget
    if widget is not None:
        widget.focus()

    set_focused(current)

# This handles mouse events, to see if they change the focus.
def mouse_handler(ev):

    x, y = ev.pos

    newfocus = None
    default = None

    for f in focus_list:

        if f.x is None:
            default = f
            continue

        if f.x <= x <= f.x + f.w and f.y <= y <= f.y + f.h:
            newfocus = f
            break
    else:
        newfocus = default

    change_focus(newfocus)


# This focuses an extreme widget, which is one of the widgets that's
# at an edge. To do this, we multiply the x, y, width, and height by
# the supplied multiplers, add them all up, and take the focus with
# the largest value.
def focus_extreme(xmul, ymul, wmul, hmul):

    max_focus = None
    max_score = -(65536**2)
        
    for f in focus_list:

        if not f.x:
            continue

        score = (f.x * xmul +
                 f.y * ymul +
                 f.w * wmul +
                 f.h * hmul)

        if score > max_score:
            max_score = score
            max_focus = f

    if max_focus:
        change_focus(max_focus)
        

# This calculates the distance between two points, applying
# the given fudge factors. The distance is left squared.
def points_dist(x0, y0, x1, y1, xfudge, yfudge):
    return (( x0 - x1 ) * xfudge ) ** 2 + \
           (( y0 - y1 ) * yfudge ) ** 2
    

# This computes the distance between two horizontal lines. (So the
# distance is either vertical, or has a vertical component to it.)
#
# The distance is left squared.
def horiz_line_dist(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1):

    # The lines overlap in x.
    if bx0 <= ax0 <= ax1 <= bx1 or \
       ax0 <= bx0 <= bx1 <= ax1 or \
       ax0 <= bx0 <= ax1 <= bx1 or \
       bx0 <= ax0 <= bx1 <= ax1:
        return (ay0 - by0) ** 2

    # The right end of a is to the left of the left end of b.
    if ax0 <= ax1 <= bx0 <= bx1:
        return points_dist(ax1, ay1, bx0, by0, renpy.config.focus_crossrange_penalty, 1.0)

    if bx0 <= bx1 <= ax0 <= ax1:
        return points_dist(ax0, ay0, bx1, by1, renpy.config.focus_crossrange_penalty, 1.0)

    assert False

# This computes the distance between two vertical lines. (So the
# distance is either hortizontal, or has a horizontal component to it.)
#
# The distance is left squared.
def verti_line_dist(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1):

    # The lines overlap in x.
    if by0 <= ay0 <= ay1 <= by1 or \
       ay0 <= by0 <= by1 <= ay1 or \
       ay0 <= by0 <= ay1 <= by1 or \
       by0 <= ay0 <= by1 <= ay1:
        return (ax0 - bx0) ** 2

    # The right end of a is to the left of the left end of b.
    if ay0 <= ay1 <= by0 <= by1:
        return points_dist(ax1, ay1, bx0, by0, 1.0, renpy.config.focus_crossrange_penalty)

    if by0 <= by1 <= ay0 <= ay1:
        return points_dist(ax0, ay0, bx1, by1, 1.0, renpy.config.focus_crossrange_penalty)

    assert False



# This focuses the widget that is nearest to the current widget. To
# determine nearest, we compute points on the widgets using the
# {from,to}_{x,y}off values. We pick the nearest, applying a fudge
# multiplier to the distances in each direction, that satisfies
# the condition (which is given a Focus object to evaluate).
#
# If no focus can be found matching the above, we look for one
# with an x of None, and make that the focus. Otherwise, we do
# nothing.
#
# If no widget is focused, we pick one and focus it.
# 
# If the current widget has an x of None, we pass things off to
# focus_extreme to deal with.
def focus_nearest(from_x0, from_y0, from_x1, from_y1,
                  to_x0, to_y0, to_x1, to_y1, 
                  line_dist,
                  condition,
                  xmul, ymul, wmul, hmul):

    if not focus_list:
        return

    # No widget focused.
    current = get_focused()

    if not current:
        change_focus(focus_list[0])
        return

    # Find the current focus.
    for f in focus_list:
        if f.widget == current:
            from_focus = f
            break
    else:
        # If we can't pick something.
        change_focus(focus_list[0])
        return

    # If placeless, focus_extreme.
    if from_focus.x is None:
        focus_extreme(xmul, ymul, wmul, hmul)
        return

    fx0 = from_focus.x + from_focus.w * from_x0
    fy0 = from_focus.y + from_focus.h * from_y0
    fx1 = from_focus.x + from_focus.w * from_x1
    fy1 = from_focus.y + from_focus.h * from_y1

    placeless = None
    new_focus = None

    # a really big number.
    new_focus_dist = (65536.0 * renpy.config.focus_crossrange_penalty) ** 2

    for f in focus_list:
        if f is from_focus:
            continue

        if f.x is None:
            placeless = f
            continue

        if not condition(from_focus, f):
            continue

        tx0 = f.x + f.w * to_x0
        ty0 = f.y + f.h * to_y0
        tx1 = f.x + f.w * to_x1
        ty1 = f.y + f.h * to_y1

        dist = line_dist(fx0, fy0, fx1, fy1,
                         tx0, ty0, tx1, ty1)
        
        if dist < new_focus_dist:
            new_focus = f
            new_focus_dist = dist

    # If we couldn't find anything, try the placeless focus.
    new_focus = new_focus or placeless

    # If we have something, switch to it.
    if new_focus:
        change_focus(new_focus)

    # And, we're done.



def key_handler(ev):

    if renpy.display.behavior.map_event(ev, 'focus_right'):
        focus_nearest(0.9, 0.1, 0.9, 0.9,
                      0.1, 0.1, 0.1, 0.9,
                      verti_line_dist,                      
                      lambda old, new : old.x + old.w <= new.x,
                      -1, 0, 0, 0)
        
    if renpy.display.behavior.map_event(ev, 'focus_left'):
        focus_nearest(0.1, 0.1, 0.1, 0.9,
                      0.9, 0.1, 0.9, 0.9,
                      verti_line_dist,
                      lambda old, new : new.x + new.w <= old.x,
                      1, 0, 1, 0)

    if renpy.display.behavior.map_event(ev, 'focus_up'):
        focus_nearest(0.1, 0.1, 0.9, 0.1,
                      0.1, 0.9, 0.9, 0.9,
                      horiz_line_dist,
                      lambda old, new : new.y + new.h <= old.y,
                      0, 1, 0, 1)

    if renpy.display.behavior.map_event(ev, 'focus_down'):
        focus_nearest(0.1, 0.9, 0.9, 0.9,
                      0.1, 0.1, 0.9, 0.1,
                      horiz_line_dist,
                      lambda old, new : old.y + old.h <= new.y,
                      0, -1, 0, 0)

        
                                


# This handles pygame events that may change focus.
def event_handler(ev):

    if ev.type in (MOUSEMOTION, MOUSEBUTTONUP, MOUSEBUTTONDOWN):
        mouse_handler(ev)

    key_handler(ev)
