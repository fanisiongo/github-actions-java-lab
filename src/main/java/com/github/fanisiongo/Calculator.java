package com.github.fanisiongo;

public final class Calculator {
    private Calculator() {
    }

    public static double calculate(double left, String operator, double right) {
        return switch (operator) {
            case "+" -> left + right;
            case "-" -> left - right;
            case "*" -> left * right;
            case "/" -> divide(left, right);
            default -> throw new IllegalArgumentException("不支持的运算符: " + operator);
        };
    }

    private static double divide(double left, double right) {
        if (right == 0) {
            throw new ArithmeticException("除数不能为 0");
        }
        return left / right;
    }
}
