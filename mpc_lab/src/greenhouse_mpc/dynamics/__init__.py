"""Discrete-time propagation of the continuous-time climate model (separate from ``physics``).

``physics`` owns the source equations; this package only (1) assembles their outputs into
dx/dt for x = [T_air, VP_air], (2) defines how controls/disturbances are held over an interval and
(3) integrates numerically. It adds no physics, no clamping and no correction terms.
"""
