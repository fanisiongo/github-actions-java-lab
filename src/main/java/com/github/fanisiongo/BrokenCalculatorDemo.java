package com.github.fanisiongo;

public final class BrokenCalculatorDemo {
    private BrokenCalculatorDemo() {
    }

    public static void demonstrateFailure() {
        Calculator.thisMethodDoesNotExist();
    }
}
