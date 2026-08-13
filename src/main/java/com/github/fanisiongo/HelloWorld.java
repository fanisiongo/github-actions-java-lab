package com.github.fanisiongo;

import java.util.Scanner;

public final class HelloWorld {
    private HelloWorld() {
    }

    public static void main(String[] args) {
        try (Scanner scanner = new Scanner(System.in)) {
            System.out.print("请输入新的第一个数字: ");
            double left = scanner.nextDouble();

            System.out.print("请输入运算符 (+, -, *, /): ");
            String operator = scanner.next();

            System.out.print("请输入第二个数字: ");
            double right = scanner.nextDouble();

            double result = Calculator.calculate(left, operator, right);
            System.out.println("计算结果: " + result);
        } catch (IllegalArgumentException | ArithmeticException exception) {
            System.out.println("计算失败: " + exception.getMessage());
        }
    }
}
