from demolib import hello


class Hello():
    def run(self):
        return hello()

    def bye(self):
        return goodbye()


if __name__ == "__main__":
    print(Hello().run())
