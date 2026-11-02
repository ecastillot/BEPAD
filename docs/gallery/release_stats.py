import bepad
from bepad.plots import plot_release_stats

test = bepad.load("test")
plot_release_stats(test, save_path="release_stats.png")
