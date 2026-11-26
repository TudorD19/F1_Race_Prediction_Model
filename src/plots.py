"""Reusable plots for the project."""
 
import matplotlib.pyplot as plt
 
# Official Pirelli colours, so every plot in the project looks the same
COMPOUND_COLORS = {
    "SOFT": "#DA291C",
    "MEDIUM": "#FFD12E",
    "HARD": "#9B9B9B",
    "INTERMEDIATE": "#43B02A",
    "WET": "#0067AD",
}
 
 
def plot_driver_laps(laps, driver_number, title=None, ax=None):
    """Scatter of lap time vs lap number for one driver, coloured by compound.
 
    `laps` must have the columns: driver_number, lap_number, lap_duration,
    compound, tyre_age.
    """
    d = laps[laps["driver_number"] == driver_number]
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, 4.5))
 
    for compound, group in d.groupby("compound"):
        ax.scatter(
            group["lap_number"],
            group["lap_duration"],
            color=COMPOUND_COLORS.get(compound, "black"),
            edgecolor="black",
            linewidth=0.5,
            s=45,
            label=compound,
        )
        # write the tyre age next to each point to see the long runs
        for _, lap in group.iterrows():
            ax.annotate(int(lap["tyre_age"]), (lap["lap_number"], lap["lap_duration"]),
                        textcoords="offset points", xytext=(0, 6),
                        ha="center", fontsize=7, color="dimgray")
 
    ax.set_xlabel("Lap number")
    ax.set_ylabel("Lap time (s)")
    ax.set_title(title or f"Driver {driver_number}")
    ax.grid(alpha=0.3)
    ax.legend(title="Compound")
    return ax
 