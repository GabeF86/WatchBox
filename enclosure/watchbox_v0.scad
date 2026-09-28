// WatchBox v0 enclosure: I2C LCD1602 on the front, ESP32 devkit on a rail on the back plate.
// Export:  openscad -D 'part="front"' -o front.stl watchbox_v0.scad   (part = "front" | "back" | "assembly")
// Units: mm. Front shell prints face-down; back plate prints flat, rail up. No supports.

part = "assembly";

// ---------- Measure your parts and edit these ----------
lcd_pcb        = [80, 36];         // LCD PCB width x height
lcd_hole_sp    = [75, 31];         // LCD mounting-hole spacing (centre to centre)
lcd_frame      = [71.3, 24.3, 7];  // display frame w x h, and how far it stands off the PCB front
lcd_back_depth = 14;               // PCB back to top of the I2C backpack (incl. pins)
esp_board      = [55, 28];         // ESP32 board length x width (measure yours!)
esp_raise      = 22;               // rail height: room for header plastic + Dupont housings + wire bend
esp_top        = 4;                // tallest part on top of the ESP32 (module / USB socket)
usb_cut        = [13, 9];          // cable plug clearance (width x height)
screw_pilot    = 2.6;              // pilot hole for M3 self-tapping (2.2 for M2.5)
screw_clear    = 3.4;              // clearance hole in the back plate
wall           = 2;
clr            = 0.3;
window_clr     = 0.5;              // extra room around the display frame
gap            = 4;                // air gap between LCD stack and ESP32 stack
button_hole    = true;             // hole in the top wall for the optional GPIO4 button
button_d       = 7;
// --------------------------------------------------------

$fn = 32;
boss_d = 7;
in_w = lcd_pcb.x + 2 * clr + 14;
in_h = lcd_pcb.y + 2 * clr + 14;
lcd_post_h = lcd_frame.z - wall;                         // frame face ends flush with the front
lcd_stack = lcd_post_h + 1.6 + lcd_back_depth;
esp_stack = esp_raise + 1.6 + esp_top;
in_d = lcd_stack + gap + esp_stack;
out = [in_w + 2 * wall, in_h + 2 * wall, in_d + wall];  // front shell, open at the back
cx = out.x / 2;
cy = out.y / 2;

// ESP32 footprint (shared by shell USB notch and back-plate rail): USB end near the right wall.
esp_x1 = wall + in_w - 1;
esp_x0 = esp_x1 - esp_board.x;
usb_z = out.z - esp_raise - 1.6 - esp_top / 2;          // USB socket centre, measured from front face

boss_pos = [for (x = [wall + boss_d / 2, out.x - wall - boss_d / 2],
                 y = [wall + boss_d / 2, out.y - wall - boss_d / 2]) [x, y]];
lcd_holes = [for (sx = [-1, 1], sy = [-1, 1]) [cx + sx * lcd_hole_sp.x / 2, cy + sy * lcd_hole_sp.y / 2]];

module rounded_box(size, r = 3) {
  hull() for (x = [r, size.x - r], y = [r, size.y - r]) translate([x, y, 0]) cylinder(r = r, h = size.z);
}

module front_shell() {
  difference() {
    union() {
      difference() {
        rounded_box(out);
        translate([wall, wall, wall]) cube([in_w, in_h, in_d + 1]);
      }
      for (p = lcd_holes) translate([p.x, p.y, wall]) cylinder(d = 5.5, h = lcd_post_h);
      for (p = boss_pos) translate([p.x, p.y, wall]) cylinder(d = boss_d, h = in_d);
    }
    // display window (the LCD frame sits in it, flush with the face)
    translate([cx - lcd_frame.x / 2 - window_clr, cy - lcd_frame.y / 2 - window_clr, -1])
      cube([lcd_frame.x + 2 * window_clr, lcd_frame.y + 2 * window_clr, wall + 2]);
    // LCD post pilot holes (blind: they don't pierce the front face)
    for (p = lcd_holes) translate([p.x, p.y, wall + 0.6]) cylinder(d = screw_pilot, h = lcd_post_h);
    // back-plate screw pilots
    for (p = boss_pos) translate([p.x, p.y, out.z - 12]) cylinder(d = screw_pilot, h = 13);
    // USB notch in the right wall, open to the back edge
    translate([out.x - wall - 1, cy - usb_cut.x / 2, usb_z - usb_cut.y / 2])
      cube([wall + 2, usb_cut.x, out.z]);
    // optional button hole in the top wall, behind the LCD stack
    if (button_hole)
      translate([cx - 25, out.y - wall - 1, wall + lcd_stack + 8])
        rotate([-90, 0, 0]) cylinder(d = button_d, h = wall + 2);
  }
}

module back_plate() {
  difference() {
    union() {
      rounded_box([out.x, out.y, wall]);
      // ESP32 rail between the pin rows; stick the board on with foam tape
      translate([esp_x0 + 4, cy - 7, wall]) cube([esp_board.x - 8, 14, esp_raise]);
      // stop at the antenna end so the board can't slide left (the right wall stops it the other way)
      translate([esp_x0 - 2, cy - 7, wall]) cube([2, 14, esp_raise + 3]);
    }
    for (p = boss_pos) translate([p.x, p.y, -1]) cylinder(d = screw_clear, h = wall + 2);
    // vent slots beside the board
    for (i = [0 : 4]) translate([cx - 30 + i * 13, cy + esp_board.y / 2 + 3, -1]) cube([6, 8, wall + 2]);
  }
}

if (part == "front") {
  front_shell();
} else if (part == "back") {
  back_plate();
} else {
  front_shell();
  color("gray") translate([0, 0, out.z + wall]) mirror([0, 0, 1]) back_plate();
}

echo(str("Outer size: ", out.x, " x ", out.y, " x ", out.z + wall, " mm"));
