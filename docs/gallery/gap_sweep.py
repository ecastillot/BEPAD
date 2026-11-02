import bepad
from bepad.plots import plot_gap_sweep

for net in ["tx", "CM", "R08"]:
    test = bepad.load("test", networks=[net])
    plot_gap_sweep(test, net, save_path=f"gap_sweep_{net}.png")
