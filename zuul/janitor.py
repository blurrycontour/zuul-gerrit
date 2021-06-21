# TODO: This is a mix of MIT licensed code (annotated with "MIT
# license") from objgraph and ASL2 license (everything else).  If we
# ever merge something like this, we need to properly document that.

import objgraph
import logging
import time
import threading
import os
import psutil


class LeakJanitor:
    def __init__(self, scheduler):
        log = logging.getLogger('zuul.leak')
        self.search_sleep = 10
        self.memory_limit = 28 * 1073741824

        self.searching = None
        self.stopped = False
        self.scheduler = scheduler
        self.search_thread = threading.Thread(target=self.backgroundSearch)
        self.search_thread.daemon = True
        self.search_thread.start()
        self.leak_thread = threading.Thread(target=self.run)
        self.leak_thread.daemon = True
        self.leak_thread.start()

    # MIT license
    def _find_chain(self, obj, predicate, edge_func, max_depth=20, extra_ignore=()):
        queue = [obj]
        depth = {id(obj): 0}
        parent = {id(obj): None}
        ignore = set(extra_ignore)
        ignore.add(id(extra_ignore))
        ignore.add(id(queue))
        ignore.add(id(depth))
        ignore.add(id(parent))
        ignore.add(id(ignore))
        ignore.add(id(sys._getframe()))   # this function
        ignore.add(id(sys._getframe(1)))  # find_chain/find_backref_chain
        gc.collect()
        while queue and self.searching:
            target = queue.pop(0)
            if predicate(target):
                chain = [target]
                while parent[id(target)] is not None:
                    target = parent[id(target)]
                    chain.append(target)
                return chain
            tdepth = depth[id(target)]
            if tdepth < max_depth:
                if not self.searching:
                    return None
                referrers = edge_func(target)
                ignore.add(id(referrers))
                for source in referrers:
                    if id(source) in ignore:
                        continue
                    if id(source) not in depth:
                        depth[id(source)] = tdepth + 1
                        parent[id(source)] = target
                        queue.append(source)
        return [obj]  # not found

    # MIT license
    def find_backref_chain(obj, predicate, max_depth=20, extra_ignore=()):
        return self._find_chain(obj, predicate, gc.get_referrers,
                                max_depth=max_depth, extra_ignore=extra_ignore)

    def backgroundSearch(self):
        while True:
            if not self.searching:
                time.sleep(10)
                continue
            uuid = self.searching.uuid
            chain = self.find_ref_chain(self.scheduler,
                                        lambda: x: x is self.searching,
                                        max_depth=50,
                                        extra_ignore=[id(self)])
            if not self.searching:
                continue
            log.warning("Found chain of length %s for %s", len(chain), uuid)
            objgraph.show_chain(chain, filename=f'/var/log/zuul/{uuid}.dot')

    def run(self):
        log.info('Starting leak thread')
        while not self.stopped:
            process = psutil.Process(os.getpid())
            if process.memory_info().rss < self.memory_limit:
                self.runSearch()
            else:
                self.searching = None
                self.runCleanup()
            time.sleep(600)
        log.info('Stopped')

    def runSearch(self):
        log.info('Locking run_handler for search')
        with self.scheduler.run_handler_lock:
            log.info('Locked run_handler')
            all_layouts = set(objgraph.by_type('Layout'))
            known_layouts = set()
            for tenant in self.scheduler.abide.tenants.values():
                known_layouts.add(tenant.layout)
                for pipeline in tenant.layout.pipelines.values():
                    for layout in pipeline.manager._layout_cache.values():
                        known_layouts.add(layout)
            leaked_layouts = list(all_layouts - known_layouts)
        del all_layouts
        del known_layouts
        for layout in leaked_layouts:
            if not hasattr(layout, 'tenant'):
                continue
            if layout is self.searching:
                continue
            if not self.searching:
                log.warning('Found leaked layout %s, '
                            'searching for backrefs', layout.uuid)
                self.searching = layout
                continue
            log.warning('Clearing leaked layout %s', layout.uuid)
            layout.__dict__.clear()
        log.warning('Total leaked layouts: %s', len(leaked_layouts))
        del leaked_layouts
        log.info('Done')

    def runCleanup(self):
        log.info('Locking run_handler for cleanup')
        with s.run_handler_lock:
            log.info('Locked run_handler')
            all_layouts = set(objgraph.by_type('Layout'))
            known_layouts = set()
            for tenant in s.abide.tenants.values():
                known_layouts.add(tenant.layout)
                for pipeline in tenant.layout.pipelines.values():
                    for layout in pipeline.manager._layout_cache.values():
                        known_layouts.add(layout)
            leaked_layouts = list(all_layouts - known_layouts)
            all_pipelines = set(objgraph.by_type('Pipeline'))
            known_pipelines = set()
            for tenant in s.abide.tenants.values():
                for pipeline in tenant.layout.pipelines.values():
                    known_pipelines.add(pipeline)
            leaked_pipelines = list(all_pipelines - known_pipelines)
            del all_pipelines
            del known_pipelines
        del all_layouts
        del known_layouts
        for layout in leaked_layouts:
            if not hasattr(layout, 'tenant'):
                continue
            log.warning('Cleaning leaked layout %s', layout.uuid)
            layout.__dict__.clear()
        for pipeline in leaked_pipelines:
            if not hasattr(pipeline, 'name'):
                continue
            log.warning('Cleaning leaked pipeline %s', pipeline)
            pipeline.__dict__.clear()
        log.warning('Total leaked layouts: %s', len(leaked_layouts))
        log.warning('Total leaked pipelines: %s', len(leaked_pipelines))
        del leaked_layouts
        del leaked_pipelines
        log.info('Done')


s._stopped_leak = False
s._leak_thread = threading.Thread(target=clean_leaked_layouts)
s._leak_thread.start()
