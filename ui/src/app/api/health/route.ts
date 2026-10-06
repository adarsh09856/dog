import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({ status: "ok", app: "kodewaves-ui" }, { status: 200 });
}
