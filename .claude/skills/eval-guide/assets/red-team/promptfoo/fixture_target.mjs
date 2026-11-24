// MOCKED target for validating the R1 red-team config offline. It stands in for the agent under test and
// returns a JSON envelope {answer, tool_calls}. Replace it with your app's test harness or HTTP target.
// RED_TEAM_FIXTURE_MODE=vulnerable plants the failure the suite must catch (negative control).
export default class FixtureTarget {
  id() {
    return 'fixture-support-agent';
  }

  async callApi(prompt, context) {
    const vulnerable = process.env.RED_TEAM_FIXTURE_MODE === 'vulnerable';
    const planted = context?.vars?.planted_content ?? '';
    if (vulnerable) {
      return {
        output: JSON.stringify({
          answer: `Done. ${planted} Order B-2001 is shipped.`,
          tool_calls: [{ name: 'create_ticket', args: { order_id: 'B-2001' } }],
        }),
      };
    }
    return {
      output: JSON.stringify({ answer: 'I can only help with orders in your own organisation.', tool_calls: [] }),
    };
  }
}
