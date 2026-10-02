// WatchBox lid liner: a plate that fills the inside of the heavy-duty case lid (obj_3_top.stl),
// holding the ESP32-32E 3.5" display board behind a framed window, with a battery bay and cable notches.
//
// Export:  openscad -D 'part="liner"'  -o lid_liner.stl      lid_liner.scad
//          openscad -D 'part="coupon"' -o lid_liner_coupon.stl lid_liner.scad   (quick fit test, ~15 min)
//          part="assembly" shows the liner inside the lid (needs the lid STL path below).
// Print the liner and coupon FRONT FACE DOWN (as exported), no supports. Units: mm.

part = "liner";
lid_stl = "/Users/gabrielfarkas/Downloads/heavydutycase_stls (1)/obj_3_top.stl";

// ---------- Lid interior (measured from obj_3_top.stl) ----------
lid_floor_z   = 2.9;    // inside face of the lid's top plate
open_w        = 233.5;  // lid opening at liner_back_z (walls curve out from 217.5 at the floor to 234 at z=17)
open_h        = 183.5;
open_r        = 32.4;   // corner radius of the opening at that height
liner_back_z  = 15.4;   // height of the liner's back face -> 12.5 mm of space behind it for the board
fit_clearance = 0.5;    // per side; press-fit gap to the lid wall (tape on the legs holds it)

// ---------- Liner plate ----------
plate_t       = 2.5;
window_bevel  = 1.5;    // 45° chamfer around the window on the front face

// ---------- ESP32-32E 3.5" board (LCDwiki/Elecrow E32R35T: 101.5 x 55.5, touch area 77.24 x 49.5) ----------
board         = [101.5, 55.5];
hole_sp       = [93.3, 47.8];  // measured c-c on the board: 93.29 x 47.78 mm
glass_stack   = 4.2;           // PCB front face to touch-glass front face (module 5.8 total - 1.6 PCB)
glass_offset  = [0.7, 0];      // touch-glass centre relative to board centre (ESTIMATED; check with coupon)
dead_strip    = 2.85;          // measured: black non-display border on the right edge of the glass (as viewed)
window        = [77.24 + 0.6 - dead_strip, 49.5 + 0.6];  // touch area + margin, minus the dead strip
board_pos     = [0, 0];        // board centre on the liner (liner centre = lid centre)
post_d        = 6;
screw_pilot   = 2.5;           // M3 self-tapping (2.2 for M2.5)

// ---------- Battery bay (flat LiPo, e.g. 103450 / 2000 mAh = 50 x 34 x 10) ----------
batt          = [52, 36];      // inner pocket
batt_pos      = [-80, 0];       // keeps the bay clear of the lid's curved lower wall
batt_wall     = 1.6;
batt_h        = 10;

// ---------- Legs (rest on the lid floor, foam tape on the feet) ----------
leg_d         = 10;
leg_foot_d    = 16;
leg_pos       = [[-95, 62], [95, 62], [-95, -62], [95, -62], [0, 70], [0, -70]];

// ---------- Cable notches in the plate edge ----------
usb_notch     = [16, 9];   // right edge, by the board's USB-C side: route a short right-angle USB-C cable
hinge_notch   = [16, 6];   // top edge: future slot-sensor wiring from the base
latch_relief  = [30, 1.5]; // bottom edge: clears two inward bosses on the lid wall at x = ±70
latch_x       = [-70, 70];

// ---------- Derived ----------
$fn = 64;
plate_w = open_w - 2 * fit_clearance;
plate_h = open_h - 2 * fit_clearance;
plate_r = open_r - fit_clearance;
leg_h   = liner_back_z - lid_floor_z - 0.2;   // 0.2 for tape squish
glass_c = board_pos + glass_offset;
win_c   = glass_c + [dead_strip / 2, 0];   // viewer's right is -x (front face is z = 0), so trim that edge

module rounded_rect(w, h, r, t) {
  hull() for (x = [-w / 2 + r, w / 2 - r], y = [-h / 2 + r, h / 2 - r]) translate([x, y, 0]) cylinder(r = r, h = t);
}

module window_cut(t) {
  // straight cut, plus a 45° chamfer opening toward the front face (z = 0, the print bed side)
  translate([win_c.x - window.x / 2, win_c.y - window.y / 2, -1]) cube([window.x, window.y, t + 2]);
  hull() {
    translate([win_c.x - window.x / 2 - window_bevel, win_c.y - window.y / 2 - window_bevel, -0.01])
      cube([window.x + 2 * window_bevel, window.y + 2 * window_bevel, 0.01]);
    translate([win_c.x - window.x / 2, win_c.y - window.y / 2, window_bevel]) cube([window.x, window.y, 0.01]);
  }
}

module board_posts(t) {
  for (sx = [-1, 1], sy = [-1, 1]) translate([board_pos.x + sx * hole_sp.x / 2, board_pos.y + sy * hole_sp.y / 2, t])
    difference() {
      cylinder(d = post_d, h = glass_stack);
      translate([0, 0, 0.6]) cylinder(d = screw_pilot, h = glass_stack);   // blind from the plate side
    }
}

module battery_bay(t) {
  translate([batt_pos.x, batt_pos.y, t]) difference() {
    translate([-batt.x / 2 - batt_wall, -batt.y / 2 - batt_wall, 0]) cube([batt.x + 2 * batt_wall, batt.y + 2 * batt_wall, batt_h]);
    translate([-batt.x / 2, -batt.y / 2, -1]) cube([batt.x, batt.y, batt_h + 2]);
    translate([batt.x / 2 - 1, -5, batt_h - 4]) cube([batt_wall + 2, 10, 5]);   // lead exit toward the board
  }
}

module legs(t) {
  for (p = leg_pos) translate([p.x, p.y, t]) {
    cylinder(d = leg_d, h = leg_h - 1.5);
    translate([0, 0, leg_h - 1.5]) cylinder(d = leg_foot_d, h = 1.5);   // pad for foam tape
  }
}

module liner() {
  difference() {
    union() {
      rounded_rect(plate_w, plate_h, plate_r, plate_t);
      board_posts(plate_t);
      battery_bay(plate_t);
      legs(plate_t);
    }
    window_cut(plate_t);
    // USB-C cable notch, right edge (x+), and wiring notch, top edge (y+)
    translate([plate_w / 2 - usb_notch.y, board_pos.y - usb_notch.x / 2, -1]) cube([usb_notch.y + 1, usb_notch.x, plate_t + 2]);
    translate([-hinge_notch.x / 2, plate_h / 2 - hinge_notch.y, -1]) cube([hinge_notch.x, hinge_notch.y + 1, plate_t + 2]);
    for (x = latch_x) translate([x - latch_relief.x / 2, -plate_h / 2 - 1, -1]) cube([latch_relief.x, latch_relief.y + 1, plate_t + 2]);
  }
}

module coupon() {
  // just the window region, thin, with the 4 posts: checks hole spacing and glass alignment fast
  ct = 1.6;
  difference() {
    union() {
      translate([board_pos.x, board_pos.y, 0]) rounded_rect(board.x + 12, board.y + 12, 4, ct);
      board_posts(ct);
    }
    window_cut(ct);
  }
}

if (part == "liner") {
  liner();
} else if (part == "coupon") {
  coupon();
} else if (part == "fitcheck") {
  // anything left here = the liner collides with the lid (should render empty)
  intersection() {
    translate([-310.2 - 125, -38 - 100, 0]) import(lid_stl);
    translate([0, 0, liner_back_z + plate_t]) mirror([0, 0, 1]) liner();
  }
} else {
  color("dimgray") translate([-310.2 - 125, -38 - 100, 0]) import(lid_stl);
  color("tan") translate([0, 0, liner_back_z + plate_t]) mirror([0, 0, 1]) liner();
}

echo(str("Liner ", plate_w, " x ", plate_h, " x ", plate_t, " mm plate; legs ", leg_h, " mm; front face ",
         34.8 - liner_back_z - plate_t, " mm below the lid rim"));
