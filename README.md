This is meant as a design too to help visualize your ideas and give you quick metrics to see if its realistic.
Its also useful for mass tracking to see if you're on track during the manufacturing process of your plane.
Save your design as a json to be able to migrate up versions.

**"Installation"**
For basic functionality: Download the AircraftDesign Tool html file and double click it to open it in your browser
For additional functionality involving airfoil analysis: Download airfoil-data-clean and heatmap-data-clean. Put those two int he same folder as the main html file.

That's it!


**Features:**

Rendering: Renders top, side and front view of a simplified model of your airplane so you can visualize the CG location, mean chord and the scale of your design.



Main math: Calculates your mass, CG, Tail sizing and more.



Extra math: Calculates your coefficient of lift and drag from a NACA 4 digit code. Also gives ballpark numbers for important speeds like stall, takeoff and cruise.



Extra extra math: Pick an airfoil from a database using colourful diagrams (found under the wing's properties).



Variables and Equations: Use variables to drive equations and equations to drive properties. Want to automatically make the spar the same length as your wingspan? Your wingspan can drive the spar length!



Mass tracking spreadsheet: Keep track of all your masses in one place and compare to different configurations using mass profiles.



Configurations: Add a new configuration to represent different states of your plane (VTOL mode, with or without payload). Choose whether you want properties to copy over or be unique.



Graph Sweep: Want to know how a dependent variable changes as you change an independent one? Graph sweep can do that! This feature is the most unstable at the moment.



Themes: Pick your favourite colours in the settings page and save your theme.



Import/Export: Use "Save JSON" and "Load". Export as "Save HTML" for a self-contained file (not compatible between versions).



**Bugs in S01.7:**

T tail warning only happens when H stab is moved by dragging, not by adjusting position values

Colour of wing wake should be something opposite to background colour, same with wing wake text.

When two parallel edges are selected for dimensioning, the dimension line should always be the perpendicular distance between them. This is not the case right now.

**No bugs that I know of in S01.7:**
Planning to add control surfaces


