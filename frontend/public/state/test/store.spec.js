import { beforeEach, describe, expect, it } from 'vitest';
import { store as globalStore } from '../store.js';

// Local factory to test store contract with isolated state
function createStore(initialState) {
  let state = { ...initialState };
  const listeners = new Set();

  function getState() {
    return state;
  }

  function setState(partialState) {
    state = { ...state, ...partialState };
    listeners.forEach((listener) => listener(state));
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return { getState, setState, subscribe };
}

describe('global store module', () => {
  it('exposes getState, setState, and subscribe', () => {
    expect(typeof globalStore.getState).toBe('function');
    expect(typeof globalStore.setState).toBe('function');
    expect(typeof globalStore.subscribe).toBe('function');
  });

  it('has expected initial shape', () => {
    const initial = globalStore.getState();
    expect(initial).toHaveProperty('projects');
    expect(Array.isArray(initial.projects)).toBe(true);
  });

  it('setState merges state on the real singleton', () => {
    const before = globalStore.getState();
    globalStore.setState({ lastGeneratedTest: '__coverage_probe__' });
    expect(globalStore.getState().lastGeneratedTest).toBe('__coverage_probe__');
    // restore
    globalStore.setState({ lastGeneratedTest: before.lastGeneratedTest });
  });

  it('subscribe receives notifications and unsubscribe stops them', () => {
    const received = [];
    const unsubscribe = globalStore.subscribe((s) => received.push(s.lastGeneratedTest));

    globalStore.setState({ lastGeneratedTest: '__probe_sub__' });
    expect(received).toHaveLength(1);
    expect(received[0]).toBe('__probe_sub__');

    unsubscribe();
    globalStore.setState({ lastGeneratedTest: null });
    expect(received).toHaveLength(1); // no new call after unsubscribe
  });
});

describe('store', () => {
  let store;

  beforeEach(() => {
    store = createStore({
      projects: [],
      activeProjectId: null,
      lastScanResult: null,
      lastGeneratedTest: null
    });
  });

  it('returns initial state', () => {
    expect(store.getState()).toEqual({
      projects: [],
      activeProjectId: null,
      lastScanResult: null,
      lastGeneratedTest: null
    });
  });

  it('merges partial state on setState', () => {
    store.setState({ activeProjectId: 5 });
    expect(store.getState().activeProjectId).toBe(5);
    expect(store.getState().projects).toEqual([]);
  });

  it('overwrites array state', () => {
    const projects = [{ id: 1, name: 'Demo' }];
    store.setState({ projects });
    expect(store.getState().projects).toEqual(projects);
  });

  it('notifies subscribers on setState', () => {
    const calls = [];
    store.subscribe((state) => calls.push(state));

    store.setState({ activeProjectId: 99 });
    expect(calls).toHaveLength(1);
    expect(calls[0].activeProjectId).toBe(99);
  });

  it('unsubscribe stops notifications', () => {
    const calls = [];
    const unsubscribe = store.subscribe((state) => calls.push(state));

    unsubscribe();
    store.setState({ activeProjectId: 1 });
    expect(calls).toHaveLength(0);
  });

  it('supports multiple independent subscribers', () => {
    const a = [];
    const b = [];
    store.subscribe((s) => a.push(s.activeProjectId));
    store.subscribe((s) => b.push(s.lastScanResult));

    store.setState({ activeProjectId: 7, lastScanResult: { total: 3 } });
    expect(a).toEqual([7]);
    expect(b).toEqual([{ total: 3 }]);
  });
});
