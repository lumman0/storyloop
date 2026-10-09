import assert from "node:assert/strict";
import { test } from "node:test";
import * as input from "../src/lib/turnInput.ts";

test("choice notes leave room for the full command and count Unicode like Python", () => {
  const optionId = "message_小林";
  const note = "😀".repeat(10000);
  const limited = input.limitChoiceNote(optionId, note);
  const command = input.choiceCommand(optionId, limited);
  assert.equal(Array.from(command).length, 10000);
  assert.equal(input.isTurnInputTooLong(command), false);
  assert.equal(input.isTurnInputTooLong(command + "😀"), true);
  assert.equal(limited.endsWith("😀"), true);
});

test("plain input allows exactly 10000 Unicode code points without splitting emoji", () => {
  assert.equal(input.limitTurnInput("😀".repeat(10001)), "😀".repeat(10000));
  assert.equal(input.limitTurnInput("a\u0301".repeat(5001)), "a\u0301".repeat(5000));
  assert.equal(input.choiceCommand("skip", "  "), "/choose skip");
  assert.equal(input.choiceCommand("talk", "  你好  "), "/choose talk 你好");
});
