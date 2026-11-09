import bepad
from bepad.plots import plot_sequence_types

for net in ["tx", "CM", "R08"]:
    test = bepad.load("test", networks=[net], scenarios=["seq-med__noise-low"])
    plot_sequence_types(test, net, save_path=f"sequences_{net}.png")
