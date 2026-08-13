package com.github.fanisiongo;

public final class BrokenCalculatorDemo {
    private BrokenCalculatorDemo() {
    }

    public static double demonstrateCalculation() {
        return Calculator.calculate(10, "+", 5);
    }
}
