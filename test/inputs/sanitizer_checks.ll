; RUN: opt -load-pass-plugin=%plugin -passes=desan-collect-checks -disable-output %s

%struct.arc = type { i64, ptr, i32 }
%struct.outer = type { i32, ptr }
%struct.inner = type { i8, i16, i64 }

declare void @__asan_report_load8(i64)
declare void @__asan_report_load16(i64)
declare void @__asan_report_load4(i64)
declare void @__asan_report_store4(i64)
declare void @__asan_load4(i64)
declare void @__asan_store8(i64)
declare void @__ubsan_handle_type_mismatch_v1(ptr, ptr)
declare void @__ubsan_handle_pointer_overflow(ptr, ptr, ptr)
declare void @__msan_warning_noreturn()
declare void @__msan_param_tls(i64)
declare void @ordinary_runtime_call()

define void @mixed_checks(ptr %p, ptr %q, i64 %idx, i1 %cond) {
entry:
  %gep = getelementptr i8, ptr %p, i64 %idx
  %addr = ptrtoint ptr %gep to i64
  call void @__asan_report_load8(i64 %addr)
  call void @__asan_report_load8(i64 %addr)
  call void @__asan_report_store4(i64 %addr)
  call void @__asan_load4(i64 %addr)
  %selected = select i1 %cond, ptr %gep, ptr %gep
  %read.value = load i32, ptr %selected, align 4
  call void @__ubsan_handle_type_mismatch_v1(ptr %p, ptr %selected)
  %overflow.ptr = getelementptr i8, ptr %q, i64 4
  store i32 %read.value, ptr %overflow.ptr, align 4
  call void @__ubsan_handle_pointer_overflow(ptr %p, ptr %q, ptr %overflow.ptr)
  %shadow = load i64, ptr %q, align 8
  call void @__msan_param_tls(i64 %shadow)
  %poisoned = icmp ne i64 %shadow, 0
  br i1 %poisoned, label %msan.warning, label %done

msan.warning:
  call void @__msan_warning_noreturn()
  br label %done

done:
  call void @ordinary_runtime_call()
  ret void
}

define void @phi_check(ptr %base, i1 %cond) {
entry:
  br i1 %cond, label %left, label %right

left:
  %left.ptr = getelementptr i8, ptr %base, i64 1
  br label %merge

right:
  %right.ptr = getelementptr i8, ptr %base, i64 2
  br label %merge

merge:
  %phi.ptr = phi ptr [ %left.ptr, %left ], [ %right.ptr, %right ]
  %phi.addr = ptrtoint ptr %phi.ptr to i64
  call void @__asan_report_load8(i64 %phi.addr)
  ret void
}

define void @invalidated_read(ptr %p, i64 %idx) {
entry:
  %gep = getelementptr i8, ptr %p, i64 %idx
  %addr = ptrtoint ptr %gep to i64
  call void @__asan_report_load8(i64 %addr)
  store i8 0, ptr %gep, align 1
  call void @__asan_report_load8(i64 %addr)
  ret void
}

define void @disjoint_static_store_between_reads(ptr %arc) {
entry:
  %head = getelementptr inbounds %struct.arc, ptr %arc, i32 0, i32 0
  %head.addr = ptrtoint ptr %head to i64
  call void @__asan_report_load8(i64 %head.addr)
  %cost = getelementptr inbounds %struct.arc, ptr %arc, i32 0, i32 2
  store i32 0, ptr %cost, align 4
  call void @__asan_report_load8(i64 %head.addr)
  ret void
}

define void @region_containment_read(ptr %p) {
entry:
  %base = ptrtoint ptr %p to i64
  call void @__asan_report_load16(i64 %base)
  %p8 = getelementptr inbounds i8, ptr %p, i64 8
  %addr8 = ptrtoint ptr %p8 to i64
  call void @__asan_report_load8(i64 %addr8)
  ret void
}

define void @loop_preheader_read(ptr %p, i64 %n) {
entry:
  %addr = ptrtoint ptr %p to i64
  call void @__asan_report_load8(i64 %addr)
  br label %loop

loop:
  %i = phi i64 [ 0, %entry ], [ %next, %loop ]
  call void @__asan_report_load8(i64 %addr)
  %next = add i64 %i, 1
  %again = icmp ult i64 %next, %n
  br i1 %again, label %loop, label %exit

exit:
  ret void
}

define void @loop_invariant_inner_read(ptr %p, i64 %n) {
entry:
  %addr = ptrtoint ptr %p to i64
  br label %loop

loop:
  %i = phi i64 [ 0, %entry ], [ %next, %loop ]
  call void @__asan_report_load8(i64 %addr)
  %next = add i64 %i, 1
  %again = icmp ult i64 %next, %n
  br i1 %again, label %loop, label %exit

exit:
  ret void
}

define void @loop_range_read(ptr %p, i64 %n) {
entry:
  %has.iterations = icmp ugt i64 %n, 0
  br i1 %has.iterations, label %preheader, label %exit

preheader:
  br label %loop

loop:
  %i = phi i64 [ 0, %preheader ], [ %next, %loop ]
  %elt = getelementptr inbounds i32, ptr %p, i64 %i
  %addr = ptrtoint ptr %elt to i64
  call void @__asan_report_load4(i64 %addr)
  %next = add nuw i64 %i, 1
  %again = icmp ult i64 %next, %n
  br i1 %again, label %loop, label %exit

exit:
  ret void
}

define void @asan_report_slice(ptr %p) {
entry:
  %addr = ptrtoint ptr %p to i64
  call void @__asan_report_load8(i64 %addr)
  %shadow.shift = lshr i64 %addr, 3
  %shadow.addr = add i64 %shadow.shift, 2147450880
  %shadow.ptr = inttoptr i64 %shadow.addr to ptr
  %shadow = load i8, ptr %shadow.ptr, align 1
  %shadow.bad = icmp ne i8 %shadow, 0
  br i1 %shadow.bad, label %asan.report, label %cont

asan.report:
  call void @__asan_report_load8(i64 %addr)
  call void asm sideeffect "", ""()
  unreachable

cont:
  ret void
}

define void @asan_struct_field_path(ptr %arc) {
entry:
  %tail = getelementptr inbounds %struct.arc, ptr %arc, i32 0, i32 1
  %addr = ptrtoint ptr %tail to i64
  call void @__asan_report_load8(i64 %addr)
  call void @__asan_store8(i64 %addr)
  ret void
}

define void @asan_nested_field_path(ptr %outer) {
entry:
  %x.addr = getelementptr inbounds %struct.outer, ptr %outer, i32 0, i32 1
  %x = load ptr, ptr %x.addr, align 8
  %y = getelementptr inbounds %struct.inner, ptr %x, i32 0, i32 2
  %addr = ptrtoint ptr %y to i64
  call void @__asan_report_load8(i64 %addr)
  ret void
}
