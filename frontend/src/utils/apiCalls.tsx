import Ajax from "./Ajax";

export let baseUrl = "";
if (import.meta.env.VITE_ENV === "prod") {
  baseUrl = "https://clinicontact.onrender.com";
}

export const createSession = async (payload: Record<string, string>) => {
  let response = null;
  try {
    response = await Ajax.req<{
      id: string;
      value: string;
      expires_at: number;
    }>({
      url: `${baseUrl}/api/v1/browser/create-session`,
      method: "POST",
      body: payload,
    });
  } catch (error) {
    console.error(error);
  }
  return response;
};

export const storeSession = async (
  sessionId: string,
  data: Record<string, string>[],
  originalUserInfo: Record<string, string>
) => {
  let response = null;
  try {
    response = await Ajax.req<Record<string, string>>({
      url: `${baseUrl}/api/v1/browser/store-session`,
      method: "POST",
      body: {
        session_id: sessionId,
        data,
        original_user_info: originalUserInfo,
      },
    });
  } catch (error) {
    console.error(error);
  }
  return response;
};

export const outboundCall = async (
  phoneNumber: string,
  userInfo: Record<string, string>
) => {
  let response = null;
  try {
    response = await Ajax.req<{ phone_call_id: string }>({
      url: `${baseUrl}/api/v1/phone/outbound-call`,
      method: "POST",
      body: {
        phone_number: phoneNumber,
        user_info: userInfo,
      },
    });
  } catch (error) {
    console.error(error);
  }
  return response;
};

export const streamSpeaker = async function* (phoneCallId: string) {
  for await (const payload of Ajax.stream<{
    timestamp: number;
    speaker: "User" | "Assistant";
  }>({
    url: `${baseUrl}/api/v1/phone/stream-speaker/${phoneCallId}`,
    method: "GET",
  })) {
    yield payload;
  }
};

export const hangUp = async (phoneCallId: string) => {
  let response = true;
  try {
    await Ajax.req({
      url: `${baseUrl}/api/v1/phone/hang-up/${phoneCallId}`,
      method: "POST",
    });
  } catch (error) {
    response = false;
    console.error(error);
  }
  return response;
};
