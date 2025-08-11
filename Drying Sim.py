import matplotlib.pyplot as plt

# ==========================================================
# REAL WORLD INPUTS - Adjust your machine's parameters here
# ==========================================================
# --- Machine Operating Conditions ---
pet_temp_c = 140.0                # Set the drying chamber temperature (°C)
cartridge_temp_c = 180.0          # Set the regeneration temperature for the offline cartridge (°C)
airflow_m3_per_min = 3.5          # Set the blower's airflow in cubic meters per minute

# --- Core Material Properties (Generally Fixed) ---
initial_pet_moisture_pct = 0.4    # Starting moisture of PET (%)
target_pet_moisture_pct = 0.1    # Your goal moisture (%)
mass_of_pet_kg = 1              # Total mass of PET pallets (kg)
mass_of_silica_g = 800.0          # Grams of silica in one cartridge
initial_silica_moisture_pct = 2   # Starting moisture of silica (%)
max_silica_capacity_pct = 25.0    # Max % moisture silica can hold
switching_time_min = 60           # How often to switch cartridges (minutes)

# --- Graph Output Settings ---
save_graph_to_file = False        # Set to True to save, False to display instantly
output_filename = 'drying_simulation_final.png'
output_dpi = 300

# =======================================================================
# DERIVED PHYSICS PARAMETERS - Converts real inputs to simulation coefficients
# =======================================================================
# This section translates the real-world settings above into the coefficients
# that the simulation engine uses. DO NOT EDIT THIS SECTION.

# 1. PET Release Coefficient (Function of PET Temperature)
# Models the exponential relationship between temperature and moisture diffusion.
# The base rate (at 100°C) is 0.005, and it increases with the 4th power of the temperature ratio.
base_pet_release_coeff = 0.005
pet_release_coefficient = base_pet_release_coeff * ((pet_temp_c / 100.0) ** 4.0)

# 2. Mass Transfer Coefficient (Function of Airflow)
# Models the linear relationship between airflow and the system's ability to move moisture.
# Calibrated based on typical blower performance.
mass_transfer_coefficient = 0.0167 * airflow_m3_per_min

# 3. Regeneration Rate (Function of Cartridge Temperature)
# Models the effective rate of water removal based on the heater temperature.
# Assumes a linear increase in effectiveness from a threshold of 120°C to a max at 160°C.
max_regen_rate = 1.75 # g/min at peak temp
regen_threshold_temp = 120.0
regen_peak_temp = 160.0
if cartridge_temp_c < regen_threshold_temp:
    regeneration_rate_g_per_min = 0.0
else:
    # Scale the rate linearly between the threshold and peak temperatures
    scale_factor = (cartridge_temp_c - regen_threshold_temp) / (regen_peak_temp - regen_threshold_temp)
    regeneration_rate_g_per_min = max_regen_rate * min(scale_factor, 1.0) # Cap at max rate

# This is a fixed simulation parameter
air_humidity_factor = 0.7

# ==========================================================
# SIMULATION ENGINE (No changes needed below this line)
# ==========================================================
time_data, pet_moisture_data, cartridge_a_data, cartridge_b_data = [], [], [], []
pet_moisture_kg = mass_of_pet_kg * (initial_pet_moisture_pct / 100.0)
cartridge_A_water_g = mass_of_silica_g * (initial_silica_moisture_pct / 100.0)
cartridge_B_water_g = mass_of_silica_g * (initial_silica_moisture_pct / 100.0)
online_cartridge, time_in_minutes, current_pet_moisture_pct = "A", 0, initial_pet_moisture_pct

while round(current_pet_moisture_pct, 4) > target_pet_moisture_pct:
    time_in_minutes += 1
    # Air humidity inside the chamber is directly proportional to the PET's current moisture.
    air_humidity_pct = current_pet_moisture_pct
    surface_concentration_pct = (cartridge_A_water_g if online_cartridge == "A" else cartridge_B_water_g) / mass_of_silica_g * 100
   # The silica's "thirst" or driving force is the difference between its max capacity and its current saturation.
    silica_driving_force = max(0, max_silica_capacity_pct - surface_concentration_pct)
    # The final demand is how thirsty the silica is, multiplied by the mass transfer efficiency,
    # and limited by the amount of moisture actually available in the air.
    moisture_demand_g = mass_transfer_coefficient * silica_driving_force * (air_humidity_pct / 100.0)
    moisture_supply_g = pet_release_coefficient * current_pet_moisture_pct
    moisture_removed_g = min(moisture_demand_g, moisture_supply_g)
    pet_moisture_kg -= moisture_removed_g / 1000.0
    if online_cartridge == "A":
        cartridge_A_water_g += moisture_removed_g
        cartridge_B_water_g = max(0, cartridge_B_water_g - regeneration_rate_g_per_min)
    else:
        cartridge_B_water_g += moisture_removed_g
        cartridge_A_water_g = max(0, cartridge_A_water_g - regeneration_rate_g_per_min)
    current_pet_moisture_pct = (pet_moisture_kg / mass_of_pet_kg) * 100.0
    time_data.append(time_in_minutes)
    pet_moisture_data.append(current_pet_moisture_pct)
    cartridge_a_data.append((cartridge_A_water_g / mass_of_silica_g) * 100.0)
    cartridge_b_data.append((cartridge_B_water_g / mass_of_silica_g) * 100.0)
    if time_in_minutes % switching_time_min == 0:
        online_cartridge = "B" if online_cartridge == "A" else "A"
    if time_in_minutes > 50000: break

print("\n--- SIMULATION FINAL RESULT ---")
print(f"INPUTS: PET Temp={pet_temp_c}°C, Cartridge Temp={cartridge_temp_c}°C, Airflow={airflow_m3_per_min} m³/min")
print(f"DERIVED: PET Release={pet_release_coefficient:.4f}, Mass Transfer={mass_transfer_coefficient:.4f}, Regen Rate={regeneration_rate_g_per_min:.2f} g/min")
if current_pet_moisture_pct <= target_pet_moisture_pct:
    print(f"✅ Success! Target reached in {time_in_minutes} minutes ({time_in_minutes / 60:.2f} hours).")
else:
    print(f"⚠️ Warning: Target not reached. After {time_in_minutes / 60:.2f} hours, final moisture was {current_pet_moisture_pct:.4f}%.")

plt.figure(figsize=(12, 8))
plt.plot(time_data, pet_moisture_data, color='red', linewidth=3, label='PET Moisture')
plt.plot(time_data, cartridge_a_data, color='blue', linestyle='--', label='Cartridge A Moisture')
plt.plot(time_data, cartridge_b_data, color='cyan', linestyle=':', label='Cartridge B Moisture')
plt.xlabel('Time (minutes)', fontsize=12)
plt.ylabel('Moisture Content (%)', fontsize=12)
plt.title('Drying Simulation Results', fontsize=16)
plt.legend()
plt.grid(True)
if save_graph_to_file:
    plt.savefig(output_filename, dpi=output_dpi, bbox_inches='tight')
    print(f"\nGraph saved to '{output_filename}'")
else:
    plt.show()