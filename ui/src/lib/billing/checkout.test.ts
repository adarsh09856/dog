import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getConfig: vi.fn(),
  createOrder: vi.fn(),
  verifyPayment: vi.fn(),
}));

vi.mock("@/lib/kodewavesApi", () => ({
  paymentsApi: {
    getConfig: mocks.getConfig,
    createOrder: mocks.createOrder,
    verifyPayment: mocks.verifyPayment,
  },
}));

import { startConfiguredCheckout } from "./checkout";

describe("configured checkout branding", () => {
  afterEach(() => {
    delete window.Razorpay;
    mocks.getConfig.mockReset();
    mocks.createOrder.mockReset();
    mocks.verifyPayment.mockReset();
  });

  it("uses the installation brand as the Razorpay checkout name", async () => {
    const open = vi.fn();
    const constructor = vi.fn(function (this: unknown, _options: unknown) {
      return { open };
    });
    window.Razorpay = constructor as unknown as NonNullable<typeof window.Razorpay>;
    mocks.getConfig.mockResolvedValue({
      razorpay_enabled: true,
      razorpay_key_id: "rzp_test",
      stripe_enabled: false,
    });
    mocks.createOrder.mockResolvedValue({
      gateway: "razorpay",
      order_id: "order_test",
      amount: 500,
      currency: "INR",
      key_id: "rzp_test",
    });
    mocks.verifyPayment.mockResolvedValue({ success: true, message: "Verified" });

    const checkout = startConfiguredCheckout({ package_id: "package-1" }, "Acme Voice");

    await vi.waitFor(() => expect(constructor).toHaveBeenCalled());
    expect(constructor).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Acme Voice" }),
    );
    expect(open).toHaveBeenCalledOnce();
    const options = constructor.mock.calls[0][0] as {
      handler: (response: { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }) => void;
    };
    options.handler({
      razorpay_payment_id: "payment_test",
      razorpay_order_id: "order_test",
      razorpay_signature: "signature_test",
    });
    await expect(checkout).resolves.toEqual({
      redirected: false,
      receipt: { success: true, message: "Verified" },
    });
  });
});
