import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json(
    { latest: null },
    {
      headers: {
        "Cache-Control": "public, max-age=3600, s-maxage=3600",
      },
    },
  );
}
