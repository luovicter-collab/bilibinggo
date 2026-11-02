// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import {
  buildActivityActions,
  buildActivityDeleteBtn,
} from "./index";

const activity = {
  dynamic_id: "100000000000000001",
  activity_title: "无法参加的测试活动",
  can_participate: true,
};

describe("activity delete action", () => {
  beforeEach(() => {
    document.body.className = "";
  });

  it("renders delete beside participate with an accessible label", () => {
    const html = buildActivityActions(activity);
    expect(html).toContain('data-action="participate"');
    expect(html).toContain('data-activity-delete="100000000000000001"');
    expect(html).toContain("aria-label=\"删除活动：无法参加的测试活动\"");
  });

  it("keeps delete available when the activity cannot participate", () => {
    const html = buildActivityActions({ ...activity, can_participate: false });
    expect(html).not.toContain('data-action="participate"');
    expect(html).toContain(">删除</button>");
  });

  it("disables delete while another job is running", () => {
    document.body.classList.add("job-running");
    const html = buildActivityDeleteBtn(activity);
    expect(html).toMatch(/data-activity-delete="100000000000000001"[\s\S]* disabled/);
  });
});
