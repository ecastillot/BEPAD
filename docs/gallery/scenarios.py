import bepad
from bepad.plots import plot_scenario_grid

for net in ["tx", "CM", "R08"]:
    test = bepad.load("test", networks=[net])
    plot_scenario_grid(test, net, save_path=f"scenarios_{net}.png")
