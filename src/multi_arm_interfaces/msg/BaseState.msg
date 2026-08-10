# M7.0.4: Mobile base state for navigation interface contract.
# In M7.0, base is fixed (is_moving=false, steering_mode="fixed").
# In M7.6, base will be differential drive (steering_mode="differential").
float64[3] position
float64[4] orientation
float64[3] linear_velocity
float64[3] angular_velocity
bool is_moving
string steering_mode