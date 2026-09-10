from .ppm import _CLI, DependsError

if __name__ == "__main__":
    from .Color_handler import Color

    c = Color()
    try:
        _CLI()
    except KeyboardInterrupt:
        print(f"{c.YELLOW}\nExitted program.{c.RESET}")
    except DependsError as e:
        print(f"{c.RED}Error while handling depends: {e}{c.RESET}")
