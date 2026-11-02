import bepad
from bepad.plots import plot_difficulty

test = bepad.load("test")                  # all networks
plot_difficulty(test, save_path="difficulty.png")
