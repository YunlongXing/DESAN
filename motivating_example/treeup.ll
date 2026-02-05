define dso_local void @update_tree(i64 noundef %cycle_ori, i64 noundef %new_orientation, i64 noundef %delta, i64 noundef %new_flow, ptr noundef %iplus, ptr noundef %jplus, ptr noundef %iminus, ptr noundef %jminus, ptr noundef %w, ptr noundef %bea, i64 noundef %sigma, i64 noundef %feas_tol) #0 {
entry:
  %cycle_ori.addr = alloca i64, align 8
  %new_orientation.addr = alloca i64, align 8
  %delta.addr = alloca i64, align 8
  %new_flow.addr = alloca i64, align 8
  %iplus.addr = alloca ptr, align 8
  %jplus.addr = alloca ptr, align 8
  %iminus.addr = alloca ptr, align 8
  %jminus.addr = alloca ptr, align 8
  %w.addr = alloca ptr, align 8
  %bea.addr = alloca ptr, align 8
  %sigma.addr = alloca i64, align 8
  %feas_tol.addr = alloca i64, align 8
  %basic_arc_temp = alloca ptr, align 8
  %new_basic_arc = alloca ptr, align 8
  %father = alloca ptr, align 8
  %temp = alloca ptr, align 8
  %new_pred = alloca ptr, align 8
  %orientation_temp = alloca i64, align 8
  %depth_temp = alloca i64, align 8
  %depth_iminus = alloca i64, align 8
  %new_depth = alloca i64, align 8
  %flow_temp = alloca i64, align 8
  store i64 %cycle_ori, ptr %cycle_ori.addr, align 8
  store i64 %new_orientation, ptr %new_orientation.addr, align 8
  store i64 %delta, ptr %delta.addr, align 8
  store i64 %new_flow, ptr %new_flow.addr, align 8
  store ptr %iplus, ptr %iplus.addr, align 8
  store ptr %jplus, ptr %jplus.addr, align 8
  store ptr %iminus, ptr %iminus.addr, align 8
  store ptr %jminus, ptr %jminus.addr, align 8
  store ptr %w, ptr %w.addr, align 8
  store ptr %bea, ptr %bea.addr, align 8
  store i64 %sigma, ptr %sigma.addr, align 8
  store i64 %feas_tol, ptr %feas_tol.addr, align 8
  call void @llvm.lifetime.start.p0(i64 8, ptr %basic_arc_temp) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %new_basic_arc) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %father) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %temp) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %new_pred) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %orientation_temp) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %depth_temp) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %depth_iminus) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %new_depth) #4
  call void @llvm.lifetime.start.p0(i64 8, ptr %flow_temp) #4
  %0 = load ptr, ptr %bea.addr, align 8
  %tail = getelementptr inbounds nuw %struct.arc, ptr %0, i32 0, i32 2
  %1 = ptrtoint ptr %tail to i64
  %2 = lshr i64 %1, 3
  %3 = add i64 %2, 2147450880
  %4 = inttoptr i64 %3 to ptr
  %5 = load i8, ptr %4, align 1
  %6 = icmp ne i8 %5, 0
  br i1 %6, label %7, label %8

7:                                                ; preds = %entry
  call void @__asan_report_load8(i64 %1) #5       ; ####### line 49, checking bea->tail
  unreachable

8:                                                ; preds = %entry
  %9 = load ptr, ptr %tail, align 8
  %10 = load ptr, ptr %jplus.addr, align 8
  %cmp = icmp eq ptr %9, %10
  br i1 %cmp, label %land.lhs.true, label %lor.lhs.false

land.lhs.true:                                    ; preds = %8
  %11 = load i64, ptr %sigma.addr, align 8
  %cmp1 = icmp slt i64 %11, 0
  br i1 %cmp1, label %if.then, label %lor.lhs.false

lor.lhs.false:                                    ; preds = %land.lhs.true, %8
  %12 = load ptr, ptr %bea.addr, align 8
  %tail2 = getelementptr inbounds nuw %struct.arc, ptr %12, i32 0, i32 2
  %13 = ptrtoint ptr %tail2 to i64
  %14 = lshr i64 %13, 3
  %15 = add i64 %14, 2147450880
  %16 = inttoptr i64 %15 to ptr
  %17 = load i8, ptr %16, align 1
  %18 = icmp ne i8 %17, 0
  br i1 %18, label %19, label %20

19:                                               ; preds = %lor.lhs.false
  call void @__asan_report_load8(i64 %13) #5      ; ####### line 50, checking bea->tail
  unreachable

20:                                               ; preds = %lor.lhs.false
  %21 = load ptr, ptr %tail2, align 8
  %22 = load ptr, ptr %iplus.addr, align 8
  %cmp3 = icmp eq ptr %21, %22
  br i1 %cmp3, label %land.lhs.true4, label %if.else

land.lhs.true4:                                   ; preds = %20
  %23 = load i64, ptr %sigma.addr, align 8
  %cmp5 = icmp sgt i64 %23, 0
  br i1 %cmp5, label %if.then, label %if.else

if.then:                                          ; preds = %land.lhs.true4, %land.lhs.true
  %24 = load i64, ptr %sigma.addr, align 8
  %cmp6 = icmp sge i64 %24, 0
  br i1 %cmp6, label %cond.true, label %cond.false

cond.true:                                        ; preds = %if.then
  %25 = load i64, ptr %sigma.addr, align 8
  br label %cond.end

cond.false:                                       ; preds = %if.then
  %26 = load i64, ptr %sigma.addr, align 8
  %sub = sub nsw i64 0, %26
  br label %cond.end

cond.end:                                         ; preds = %cond.false, %cond.true
  %cond = phi i64 [ %25, %cond.true ], [ %sub, %cond.false ]
  store i64 %cond, ptr %sigma.addr, align 8
  br label %if.end

if.else:                                          ; preds = %land.lhs.true4, %20
  %27 = load i64, ptr %sigma.addr, align 8
  %cmp7 = icmp sge i64 %27, 0
  br i1 %cmp7, label %cond.true8, label %cond.false9

cond.true8:                                       ; preds = %if.else
  %28 = load i64, ptr %sigma.addr, align 8
  br label %cond.end11

cond.false9:                                      ; preds = %if.else
  %29 = load i64, ptr %sigma.addr, align 8
  %sub10 = sub nsw i64 0, %29
  br label %cond.end11

cond.end11:                                       ; preds = %cond.false9, %cond.true8
  %cond12 = phi i64 [ %28, %cond.true8 ], [ %sub10, %cond.false9 ]
  %sub13 = sub nsw i64 0, %cond12
  store i64 %sub13, ptr %sigma.addr, align 8
  br label %if.end

if.end:                                           ; preds = %cond.end11, %cond.end
  %30 = load ptr, ptr %iminus.addr, align 8
  store ptr %30, ptr %father, align 8
  %31 = load i64, ptr %sigma.addr, align 8
  %32 = load ptr, ptr %father, align 8
  %potential = getelementptr inbounds nuw %struct.node, ptr %32, i32 0, i32 0
  %33 = ptrtoint ptr %potential to i64
  %34 = lshr i64 %33, 3
  %35 = add i64 %34, 2147450880
  %36 = inttoptr i64 %35 to ptr
  %37 = load i8, ptr %36, align 1
  %38 = icmp ne i8 %37, 0
  br i1 %38, label %39, label %40

39:                                               ; preds = %if.end
  call void @__asan_report_load8(i64 %33) #5      ; ####### line 55, checking father->potential
  unreachable

40:                                               ; preds = %if.end
  %41 = load i64, ptr %potential, align 8
  %add = add nsw i64 %41, %31
  store i64 %add, ptr %potential, align 8
  br label %RECURSION

RECURSION:                                        ; preds = %62, %40
  %42 = load ptr, ptr %father, align 8
  %child = getelementptr inbounds nuw %struct.node, ptr %42, i32 0, i32 2
  %43 = ptrtoint ptr %child to i64
  %44 = lshr i64 %43, 3
  %45 = add i64 %44, 2147450880
  %46 = inttoptr i64 %45 to ptr
  %47 = load i8, ptr %46, align 1
  %48 = icmp ne i8 %47, 0
  br i1 %48, label %49, label %50

49:                                               ; preds = %RECURSION
  call void @__asan_report_load8(i64 %43) #5      ; ####### line 58, chekcing father->child
  unreachable

50:                                               ; preds = %RECURSION
  %51 = load ptr, ptr %child, align 8
  store ptr %51, ptr %temp, align 8
  %52 = load ptr, ptr %temp, align 8
  %tobool = icmp ne ptr %52, null
  br i1 %tobool, label %if.then14, label %if.end17

if.then14:                                        ; preds = %50
  br label %ITERATION

ITERATION:                                        ; preds = %if.then22, %if.then14
  %53 = load i64, ptr %sigma.addr, align 8
  %54 = load ptr, ptr %temp, align 8
  %potential15 = getelementptr inbounds nuw %struct.node, ptr %54, i32 0, i32 0
  %55 = ptrtoint ptr %potential15 to i64
  %56 = lshr i64 %55, 3
  %57 = add i64 %56, 2147450880
  %58 = inttoptr i64 %57 to ptr
  %59 = load i8, ptr %58, align 1
  %60 = icmp ne i8 %59, 0
  br i1 %60, label %61, label %62

61:                                               ; preds = %ITERATION
  call void @__asan_report_load8(i64 %55) #5      ; ####### line 62, checking temp->potential
  unreachable

62:                                               ; preds = %ITERATION
  %63 = load i64, ptr %potential15, align 8
  %add16 = add nsw i64 %63, %53
  store i64 %add16, ptr %potential15, align 8
  %64 = load ptr, ptr %temp, align 8
  store ptr %64, ptr %father, align 8
  br label %RECURSION

if.end17:                                         ; preds = %50
  br label %TEST

TEST:                                             ; preds = %86, %if.end17
  %65 = load ptr, ptr %father, align 8
  %66 = load ptr, ptr %iminus.addr, align 8
  %cmp18 = icmp eq ptr %65, %66
  br i1 %cmp18, label %if.then19, label %if.end20

if.then19:                                        ; preds = %TEST
  br label %CONTINUE

if.end20:                                         ; preds = %TEST
  %67 = load ptr, ptr %father, align 8
  %sibling = getelementptr inbounds nuw %struct.node, ptr %67, i32 0, i32 4
  %68 = ptrtoint ptr %sibling to i64
  %69 = lshr i64 %68, 3
  %70 = add i64 %69, 2147450880
  %71 = inttoptr i64 %70 to ptr
  %72 = load i8, ptr %71, align 1
  %73 = icmp ne i8 %72, 0
  br i1 %73, label %74, label %75

74:                                               ; preds = %if.end20
  call void @__asan_report_load8(i64 %68) #5      ; ####### line 69, checking father->sibling
  unreachable

75:                                               ; preds = %if.end20
  %76 = load ptr, ptr %sibling, align 8
  store ptr %76, ptr %temp, align 8
  %77 = load ptr, ptr %temp, align 8
  %tobool21 = icmp ne ptr %77, null
  br i1 %tobool21, label %if.then22, label %if.end23

if.then22:                                        ; preds = %75
  br label %ITERATION

if.end23:                                         ; preds = %75
  %78 = load ptr, ptr %father, align 8
  %pred = getelementptr inbounds nuw %struct.node, ptr %78, i32 0, i32 3
  %79 = ptrtoint ptr %pred to i64
  %80 = lshr i64 %79, 3
  %81 = add i64 %80, 2147450880
  %82 = inttoptr i64 %81 to ptr
  %83 = load i8, ptr %82, align 1
  %84 = icmp ne i8 %83, 0
  br i1 %84, label %85, label %86

85:                                               ; preds = %if.end23
  call void @__asan_report_load8(i64 %79) #5      ; ####### line 72, checking father->pred
  unreachable

86:                                               ; preds = %if.end23
  %87 = load ptr, ptr %pred, align 8
  store ptr %87, ptr %father, align 8
  br label %TEST

CONTINUE:                                         ; preds = %if.then19
  %88 = load ptr, ptr %iplus.addr, align 8
  store ptr %88, ptr %temp, align 8
  %89 = load ptr, ptr %temp, align 8
  %pred24 = getelementptr inbounds nuw %struct.node, ptr %89, i32 0, i32 3
  %90 = ptrtoint ptr %pred24 to i64
  %91 = lshr i64 %90, 3
  %92 = add i64 %91, 2147450880
  %93 = inttoptr i64 %92 to ptr
  %94 = load i8, ptr %93, align 1
  %95 = icmp ne i8 %94, 0
  br i1 %95, label %96, label %97

96:                                               ; preds = %CONTINUE
  call void @__asan_report_load8(i64 %90) #5      ; ####### line 80, checking temp->pred
  unreachable

97:                                               ; preds = %CONTINUE
  %98 = load ptr, ptr %pred24, align 8
  store ptr %98, ptr %father, align 8
  %99 = load ptr, ptr %iminus.addr, align 8
  %depth = getelementptr inbounds nuw %struct.node, ptr %99, i32 0, i32 11
  %100 = ptrtoint ptr %depth to i64
  %101 = lshr i64 %100, 3
  %102 = add i64 %101, 2147450880
  %103 = inttoptr i64 %102 to ptr
  %104 = load i8, ptr %103, align 1
  %105 = icmp ne i8 %104, 0
  br i1 %105, label %106, label %107

106:                                              ; preds = %97
  call void @__asan_report_load8(i64 %100) #5     ; ####### line 81, checking iminus->depth
  unreachable

107:                                              ; preds = %97
  %108 = load i64, ptr %depth, align 8
  store i64 %108, ptr %depth_iminus, align 8
  store i64 %108, ptr %new_depth, align 8
  %109 = load ptr, ptr %jplus.addr, align 8
  store ptr %109, ptr %new_pred, align 8
  %110 = load ptr, ptr %bea.addr, align 8
  store ptr %110, ptr %new_basic_arc, align 8
  br label %while.cond

while.cond:                                       ; preds = %404, %107
  %111 = load ptr, ptr %temp, align 8
  %112 = load ptr, ptr %jminus.addr, align 8
  %cmp25 = icmp ne ptr %111, %112
  br i1 %cmp25, label %while.body, label %while.end

while.body:                                       ; preds = %while.cond
  %113 = load ptr, ptr %temp, align 8
  %sibling26 = getelementptr inbounds nuw %struct.node, ptr %113, i32 0, i32 4
  %114 = ptrtoint ptr %sibling26 to i64
  %115 = lshr i64 %114, 3
  %116 = add i64 %115, 2147450880
  %117 = inttoptr i64 %116 to ptr
  %118 = load i8, ptr %117, align 1
  %119 = icmp ne i8 %118, 0
  br i1 %119, label %120, label %121

120:                                              ; preds = %while.body
  call void @__asan_report_load8(i64 %114) #5     ; ####### line 86, checking temp->sibling
  unreachable

121:                                              ; preds = %while.body
  %122 = load ptr, ptr %sibling26, align 8
  %tobool27 = icmp ne ptr %122, null
  br i1 %tobool27, label %if.then28, label %if.end31

if.then28:                                        ; preds = %121
  %123 = load ptr, ptr %temp, align 8
  %sibling_prev = getelementptr inbounds nuw %struct.node, ptr %123, i32 0, i32 5
  %124 = ptrtoint ptr %sibling_prev to i64
  %125 = lshr i64 %124, 3
  %126 = add i64 %125, 2147450880
  %127 = inttoptr i64 %126 to ptr
  %128 = load i8, ptr %127, align 1
  %129 = icmp ne i8 %128, 0
  br i1 %129, label %130, label %131

130:                                              ; preds = %if.then28
  call void @__asan_report_load8(i64 %124) #5     ; ####### line 87, checking temp->sibling_prev
  unreachable

131:                                              ; preds = %if.then28
  %132 = load ptr, ptr %sibling_prev, align 8
  %133 = load ptr, ptr %temp, align 8
  %sibling29 = getelementptr inbounds nuw %struct.node, ptr %133, i32 0, i32 4
  %134 = ptrtoint ptr %sibling29 to i64
  %135 = lshr i64 %134, 3
  %136 = add i64 %135, 2147450880
  %137 = inttoptr i64 %136 to ptr
  %138 = load i8, ptr %137, align 1
  %139 = icmp ne i8 %138, 0
  br i1 %139, label %140, label %141

140:                                              ; preds = %131
  call void @__asan_report_load8(i64 %134) #5     ; ####### line 87, checking temp->sibling
  unreachable

141:                                              ; preds = %131
  %142 = load ptr, ptr %sibling29, align 8
  %sibling_prev30 = getelementptr inbounds nuw %struct.node, ptr %142, i32 0, i32 5
  %143 = ptrtoint ptr %sibling_prev30 to i64
  %144 = lshr i64 %143, 3
  %145 = add i64 %144, 2147450880
  %146 = inttoptr i64 %145 to ptr
  %147 = load i8, ptr %146, align 1
  %148 = icmp ne i8 %147, 0
  br i1 %148, label %149, label %150

149:                                              ; preds = %141
  call void @__asan_report_store8(i64 %143) #5    ; ####### line 87, checking temp->sibling->sibling_prev
  unreachable

150:                                              ; preds = %141
  store ptr %132, ptr %sibling_prev30, align 8
  br label %if.end31

if.end31:                                         ; preds = %150, %121
  %151 = load ptr, ptr %temp, align 8
  %sibling_prev32 = getelementptr inbounds nuw %struct.node, ptr %151, i32 0, i32 5
  %152 = ptrtoint ptr %sibling_prev32 to i64
  %153 = lshr i64 %152, 3
  %154 = add i64 %153, 2147450880
  %155 = inttoptr i64 %154 to ptr
  %156 = load i8, ptr %155, align 1
  %157 = icmp ne i8 %156, 0
  br i1 %157, label %158, label %159

158:                                              ; preds = %if.end31
  call void @__asan_report_load8(i64 %152) #5     ; ####### line 88, checking temp->sibling_prev
  unreachable

159:                                              ; preds = %if.end31
  %160 = load ptr, ptr %sibling_prev32, align 8
  %tobool33 = icmp ne ptr %160, null
  br i1 %tobool33, label %if.then34, label %if.else38

if.then34:                                        ; preds = %159
  %161 = load ptr, ptr %temp, align 8
  %sibling35 = getelementptr inbounds nuw %struct.node, ptr %161, i32 0, i32 4
  %162 = ptrtoint ptr %sibling35 to i64
  %163 = lshr i64 %162, 3
  %164 = add i64 %163, 2147450880
  %165 = inttoptr i64 %164 to ptr
  %166 = load i8, ptr %165, align 1
  %167 = icmp ne i8 %166, 0
  br i1 %167, label %168, label %169

168:                                              ; preds = %if.then34
  call void @__asan_report_load8(i64 %162) #5     ; ####### line 89, checking temp->sibling
  unreachable

169:                                              ; preds = %if.then34
  %170 = load ptr, ptr %sibling35, align 8
  %171 = load ptr, ptr %temp, align 8
  %sibling_prev36 = getelementptr inbounds nuw %struct.node, ptr %171, i32 0, i32 5
  %172 = ptrtoint ptr %sibling_prev36 to i64
  %173 = lshr i64 %172, 3
  %174 = add i64 %173, 2147450880
  %175 = inttoptr i64 %174 to ptr
  %176 = load i8, ptr %175, align 1
  %177 = icmp ne i8 %176, 0
  br i1 %177, label %178, label %179

178:                                              ; preds = %169
  call void @__asan_report_load8(i64 %172) #5     ; ####### line 89, checking temp->sibling_prev
  unreachable

179:                                              ; preds = %169
  %180 = load ptr, ptr %sibling_prev36, align 8
  %sibling37 = getelementptr inbounds nuw %struct.node, ptr %180, i32 0, i32 4
  %181 = ptrtoint ptr %sibling37 to i64
  %182 = lshr i64 %181, 3
  %183 = add i64 %182, 2147450880
  %184 = inttoptr i64 %183 to ptr
  %185 = load i8, ptr %184, align 1
  %186 = icmp ne i8 %185, 0
  br i1 %186, label %187, label %188

187:                                              ; preds = %179
  call void @__asan_report_store8(i64 %181) #5    ; ####### line 89, checking temp->sibling_prev->sibling
  unreachable

188:                                              ; preds = %179
  store ptr %170, ptr %sibling37, align 8
  br label %if.end41

if.else38:                                        ; preds = %159
  %189 = load ptr, ptr %temp, align 8
  %sibling39 = getelementptr inbounds nuw %struct.node, ptr %189, i32 0, i32 4
  %190 = ptrtoint ptr %sibling39 to i64
  %191 = lshr i64 %190, 3
  %192 = add i64 %191, 2147450880
  %193 = inttoptr i64 %192 to ptr
  %194 = load i8, ptr %193, align 1
  %195 = icmp ne i8 %194, 0
  br i1 %195, label %196, label %197

196:                                              ; preds = %if.else38
  call void @__asan_report_load8(i64 %190) #5     ; ####### line 90, checking temp->sibling
  unreachable

197:                                              ; preds = %if.else38
  %198 = load ptr, ptr %sibling39, align 8
  %199 = load ptr, ptr %father, align 8
  %child40 = getelementptr inbounds nuw %struct.node, ptr %199, i32 0, i32 2
  %200 = ptrtoint ptr %child40 to i64
  %201 = lshr i64 %200, 3
  %202 = add i64 %201, 2147450880
  %203 = inttoptr i64 %202 to ptr
  %204 = load i8, ptr %203, align 1
  %205 = icmp ne i8 %204, 0
  br i1 %205, label %206, label %207

206:                                              ; preds = %197
  call void @__asan_report_store8(i64 %200) #5    ; ####### line 90, checking father->child
  unreachable

207:                                              ; preds = %197
  store ptr %198, ptr %child40, align 8
  br label %if.end41

if.end41:                                         ; preds = %207, %188
  %208 = load ptr, ptr %new_pred, align 8
  %209 = load ptr, ptr %temp, align 8
  %pred42 = getelementptr inbounds nuw %struct.node, ptr %209, i32 0, i32 3
  %210 = ptrtoint ptr %pred42 to i64
  %211 = lshr i64 %210, 3
  %212 = add i64 %211, 2147450880
  %213 = inttoptr i64 %212 to ptr
  %214 = load i8, ptr %213, align 1
  %215 = icmp ne i8 %214, 0
  br i1 %215, label %216, label %217

216:                                              ; preds = %if.end41
  call void @__asan_report_store8(i64 %210) #5    ; ####### line 93, checking temp->pred
  unreachable

217:                                              ; preds = %if.end41
  store ptr %208, ptr %pred42, align 8
  %218 = load ptr, ptr %new_pred, align 8
  %child43 = getelementptr inbounds nuw %struct.node, ptr %218, i32 0, i32 2
  %219 = ptrtoint ptr %child43 to i64
  %220 = lshr i64 %219, 3
  %221 = add i64 %220, 2147450880
  %222 = inttoptr i64 %221 to ptr
  %223 = load i8, ptr %222, align 1
  %224 = icmp ne i8 %223, 0
  br i1 %224, label %225, label %226

225:                                              ; preds = %217
  call void @__asan_report_load8(i64 %219) #5     ; ####### line 94, checking new_pred->child
  unreachable

226:                                              ; preds = %217
  %227 = load ptr, ptr %child43, align 8
  %228 = load ptr, ptr %temp, align 8
  %sibling44 = getelementptr inbounds nuw %struct.node, ptr %228, i32 0, i32 4
  %229 = ptrtoint ptr %sibling44 to i64
  %230 = lshr i64 %229, 3
  %231 = add i64 %230, 2147450880
  %232 = inttoptr i64 %231 to ptr
  %233 = load i8, ptr %232, align 1
  %234 = icmp ne i8 %233, 0
  br i1 %234, label %235, label %236

235:                                              ; preds = %226
  call void @__asan_report_store8(i64 %229) #5    ; ####### line 94, checking temp->sibling
  unreachable

236:                                              ; preds = %226
  store ptr %227, ptr %sibling44, align 8
  %237 = load ptr, ptr %temp, align 8
  %sibling45 = getelementptr inbounds nuw %struct.node, ptr %237, i32 0, i32 4
  %238 = ptrtoint ptr %sibling45 to i64
  %239 = lshr i64 %238, 3
  %240 = add i64 %239, 2147450880
  %241 = inttoptr i64 %240 to ptr
  %242 = load i8, ptr %241, align 1
  %243 = icmp ne i8 %242, 0
  br i1 %243, label %244, label %245

244:                                              ; preds = %236
  call void @__asan_report_load8(i64 %238) #5     ; ####### line 95, checking temp->sibling
  unreachable

245:                                              ; preds = %236
  %246 = load ptr, ptr %sibling45, align 8
  %tobool46 = icmp ne ptr %246, null
  br i1 %tobool46, label %if.then47, label %if.end50

if.then47:                                        ; preds = %245
  %247 = load ptr, ptr %temp, align 8
  %248 = load ptr, ptr %temp, align 8
  %sibling48 = getelementptr inbounds nuw %struct.node, ptr %248, i32 0, i32 4
  %249 = ptrtoint ptr %sibling48 to i64
  %250 = lshr i64 %249, 3
  %251 = add i64 %250, 2147450880
  %252 = inttoptr i64 %251 to ptr
  %253 = load i8, ptr %252, align 1
  %254 = icmp ne i8 %253, 0
  br i1 %254, label %255, label %256

255:                                              ; preds = %if.then47
  call void @__asan_report_load8(i64 %249) #5     ; ####### line 96, checking temp->sibling
  unreachable

256:                                              ; preds = %if.then47
  %257 = load ptr, ptr %sibling48, align 8
  %sibling_prev49 = getelementptr inbounds nuw %struct.node, ptr %257, i32 0, i32 5
  %258 = ptrtoint ptr %sibling_prev49 to i64
  %259 = lshr i64 %258, 3
  %260 = add i64 %259, 2147450880
  %261 = inttoptr i64 %260 to ptr
  %262 = load i8, ptr %261, align 1
  %263 = icmp ne i8 %262, 0
  br i1 %263, label %264, label %265

264:                                              ; preds = %256
  call void @__asan_report_store8(i64 %258) #5    ; ####### line 96, checking temp->sibling->sibling_prev
  unreachable

265:                                              ; preds = %256
  store ptr %247, ptr %sibling_prev49, align 8
  br label %if.end50

if.end50:                                         ; preds = %265, %245
  %266 = load ptr, ptr %temp, align 8
  %267 = load ptr, ptr %new_pred, align 8
  %child51 = getelementptr inbounds nuw %struct.node, ptr %267, i32 0, i32 2
  %268 = ptrtoint ptr %child51 to i64
  %269 = lshr i64 %268, 3
  %270 = add i64 %269, 2147450880
  %271 = inttoptr i64 %270 to ptr
  %272 = load i8, ptr %271, align 1
  %273 = icmp ne i8 %272, 0
  br i1 %273, label %274, label %275

274:                                              ; preds = %if.end50
  call void @__asan_report_store8(i64 %268) #5    ; ####### line 97, checking new_pred->child
  unreachable

275:                                              ; preds = %if.end50
  store ptr %266, ptr %child51, align 8
  %276 = load ptr, ptr %temp, align 8
  %sibling_prev52 = getelementptr inbounds nuw %struct.node, ptr %276, i32 0, i32 5
  %277 = ptrtoint ptr %sibling_prev52 to i64
  %278 = lshr i64 %277, 3
  %279 = add i64 %278, 2147450880
  %280 = inttoptr i64 %279 to ptr
  %281 = load i8, ptr %280, align 1
  %282 = icmp ne i8 %281, 0
  br i1 %282, label %283, label %284

283:                                              ; preds = %275
  call void @__asan_report_store8(i64 %277) #5    ; ####### line 98, checking temp->sibling_prev
  unreachable

284:                                              ; preds = %275
  store ptr null, ptr %sibling_prev52, align 8
  %285 = load ptr, ptr %temp, align 8
  %orientation = getelementptr inbounds nuw %struct.node, ptr %285, i32 0, i32 1
  %286 = ptrtoint ptr %orientation to i64
  %287 = lshr i64 %286, 3
  %288 = add i64 %287, 2147450880
  %289 = inttoptr i64 %288 to ptr
  %290 = load i8, ptr %289, align 1
  %291 = icmp ne i8 %290, 0
  br i1 %291, label %292, label %298, !prof !7

292:                                              ; preds = %284
  %293 = and i64 %286, 7
  %294 = add i64 %293, 3
  %295 = trunc i64 %294 to i8
  %296 = icmp sge i8 %295, %290
  br i1 %296, label %297, label %298

297:                                              ; preds = %292
  call void @__asan_report_load4(i64 %286) #5     ; ####### line 100, checking temp->orientation
  unreachable

298:                                              ; preds = %292, %284
  %299 = load i32, ptr %orientation, align 8
  %tobool53 = icmp ne i32 %299, 0
  %lnot = xor i1 %tobool53, true
  %lnot.ext = zext i1 %lnot to i32
  %conv = sext i32 %lnot.ext to i64
  store i64 %conv, ptr %orientation_temp, align 8
  %300 = load i64, ptr %orientation_temp, align 8
  %301 = load i64, ptr %cycle_ori.addr, align 8
  %cmp54 = icmp eq i64 %300, %301
  br i1 %cmp54, label %if.then56, label %if.else58

if.then56:                                        ; preds = %298
  %302 = load ptr, ptr %temp, align 8
  %flow = getelementptr inbounds nuw %struct.node, ptr %302, i32 0, i32 10
  %303 = ptrtoint ptr %flow to i64
  %304 = lshr i64 %303, 3
  %305 = add i64 %304, 2147450880
  %306 = inttoptr i64 %305 to ptr
  %307 = load i8, ptr %306, align 1
  %308 = icmp ne i8 %307, 0
  br i1 %308, label %309, label %310

309:                                              ; preds = %if.then56
  call void @__asan_report_load8(i64 %303) #5     ; ####### line 102, checking temp->flow
  unreachable

310:                                              ; preds = %if.then56
  %311 = load i64, ptr %flow, align 8
  %312 = load i64, ptr %delta.addr, align 8
  %add57 = add nsw i64 %311, %312
  store i64 %add57, ptr %flow_temp, align 8
  br label %if.end61

if.else58:                                        ; preds = %298
  %313 = load ptr, ptr %temp, align 8
  %flow59 = getelementptr inbounds nuw %struct.node, ptr %313, i32 0, i32 10
  %314 = ptrtoint ptr %flow59 to i64
  %315 = lshr i64 %314, 3
  %316 = add i64 %315, 2147450880
  %317 = inttoptr i64 %316 to ptr
  %318 = load i8, ptr %317, align 1
  %319 = icmp ne i8 %318, 0
  br i1 %319, label %320, label %321

320:                                              ; preds = %if.else58
  call void @__asan_report_load8(i64 %314) #5     ; ####### line 104, checking temp->flow
  unreachable

321:                                              ; preds = %if.else58
  %322 = load i64, ptr %flow59, align 8
  %323 = load i64, ptr %delta.addr, align 8
  %sub60 = sub nsw i64 %322, %323
  store i64 %sub60, ptr %flow_temp, align 8
  br label %if.end61

if.end61:                                         ; preds = %321, %310
  %324 = load ptr, ptr %temp, align 8
  %basic_arc = getelementptr inbounds nuw %struct.node, ptr %324, i32 0, i32 6
  %325 = ptrtoint ptr %basic_arc to i64
  %326 = lshr i64 %325, 3
  %327 = add i64 %326, 2147450880
  %328 = inttoptr i64 %327 to ptr
  %329 = load i8, ptr %328, align 1
  %330 = icmp ne i8 %329, 0
  br i1 %330, label %331, label %332

331:                                              ; preds = %if.end61
  call void @__asan_report_load8(i64 %325) #5     ; ####### line 105, checking temp->basic_arc
  unreachable

332:                                              ; preds = %if.end61
  %333 = load ptr, ptr %basic_arc, align 8
  store ptr %333, ptr %basic_arc_temp, align 8
  %334 = load ptr, ptr %temp, align 8
  %depth62 = getelementptr inbounds nuw %struct.node, ptr %334, i32 0, i32 11
  %335 = ptrtoint ptr %depth62 to i64
  %336 = lshr i64 %335, 3
  %337 = add i64 %336, 2147450880
  %338 = inttoptr i64 %337 to ptr
  %339 = load i8, ptr %338, align 1
  %340 = icmp ne i8 %339, 0
  br i1 %340, label %341, label %342

341:                                              ; preds = %332
  call void @__asan_report_load8(i64 %335) #5     ; ####### line 106, checking temp->depth
  unreachable

342:                                              ; preds = %332
  %343 = load i64, ptr %depth62, align 8
  store i64 %343, ptr %depth_temp, align 8
  %344 = load i64, ptr %new_orientation.addr, align 8
  %conv63 = trunc i64 %344 to i32
  %345 = load ptr, ptr %temp, align 8
  %orientation64 = getelementptr inbounds nuw %struct.node, ptr %345, i32 0, i32 1
  %346 = ptrtoint ptr %orientation64 to i64
  %347 = lshr i64 %346, 3
  %348 = add i64 %347, 2147450880
  %349 = inttoptr i64 %348 to ptr
  %350 = load i8, ptr %349, align 1
  %351 = icmp ne i8 %350, 0
  br i1 %351, label %352, label %358, !prof !7

352:                                              ; preds = %342
  %353 = and i64 %346, 7
  %354 = add i64 %353, 3
  %355 = trunc i64 %354 to i8
  %356 = icmp sge i8 %355, %350
  br i1 %356, label %357, label %358

357:                                              ; preds = %352
  call void @__asan_report_store4(i64 %346) #5    ; ####### line 108, checking temp->orientation
  unreachable

358:                                              ; preds = %352, %342
  store i32 %conv63, ptr %orientation64, align 8
  %359 = load i64, ptr %new_flow.addr, align 8
  %360 = load ptr, ptr %temp, align 8
  %flow65 = getelementptr inbounds nuw %struct.node, ptr %360, i32 0, i32 10
  %361 = ptrtoint ptr %flow65 to i64
  %362 = lshr i64 %361, 3
  %363 = add i64 %362, 2147450880
  %364 = inttoptr i64 %363 to ptr
  %365 = load i8, ptr %364, align 1
  %366 = icmp ne i8 %365, 0
  br i1 %366, label %367, label %368

367:                                              ; preds = %358
  call void @__asan_report_store8(i64 %361) #5    ; ####### line 109, checking temp->flow
  unreachable

368:                                              ; preds = %358
  store i64 %359, ptr %flow65, align 8
  %369 = load ptr, ptr %new_basic_arc, align 8
  %370 = load ptr, ptr %temp, align 8
  %basic_arc66 = getelementptr inbounds nuw %struct.node, ptr %370, i32 0, i32 6
  %371 = ptrtoint ptr %basic_arc66 to i64
  %372 = lshr i64 %371, 3
  %373 = add i64 %372, 2147450880
  %374 = inttoptr i64 %373 to ptr
  %375 = load i8, ptr %374, align 1
  %376 = icmp ne i8 %375, 0
  br i1 %376, label %377, label %378

377:                                              ; preds = %368
  call void @__asan_report_store8(i64 %371) #5    ; ####### line 110, checking temp->basic_arc
  unreachable

378:                                              ; preds = %368
  store ptr %369, ptr %basic_arc66, align 8
  %379 = load i64, ptr %new_depth, align 8
  %380 = load ptr, ptr %temp, align 8
  %depth67 = getelementptr inbounds nuw %struct.node, ptr %380, i32 0, i32 11
  %381 = ptrtoint ptr %depth67 to i64
  %382 = lshr i64 %381, 3
  %383 = add i64 %382, 2147450880
  %384 = inttoptr i64 %383 to ptr
  %385 = load i8, ptr %384, align 1
  %386 = icmp ne i8 %385, 0
  br i1 %386, label %387, label %388

387:                                              ; preds = %378
  call void @__asan_report_store8(i64 %381) #5    ; ####### line 111, checking temp->depth
  unreachable

388:                                              ; preds = %378
  store i64 %379, ptr %depth67, align 8
  %389 = load ptr, ptr %temp, align 8
  store ptr %389, ptr %new_pred, align 8
  %390 = load i64, ptr %orientation_temp, align 8
  store i64 %390, ptr %new_orientation.addr, align 8
  %391 = load i64, ptr %flow_temp, align 8
  store i64 %391, ptr %new_flow.addr, align 8
  %392 = load ptr, ptr %basic_arc_temp, align 8
  store ptr %392, ptr %new_basic_arc, align 8
  %393 = load i64, ptr %depth_iminus, align 8
  %394 = load i64, ptr %depth_temp, align 8
  %sub68 = sub nsw i64 %393, %394
  store i64 %sub68, ptr %new_depth, align 8
  %395 = load ptr, ptr %father, align 8
  store ptr %395, ptr %temp, align 8
  %396 = load ptr, ptr %temp, align 8
  %pred69 = getelementptr inbounds nuw %struct.node, ptr %396, i32 0, i32 3
  %397 = ptrtoint ptr %pred69 to i64
  %398 = lshr i64 %397, 3
  %399 = add i64 %398, 2147450880
  %400 = inttoptr i64 %399 to ptr
  %401 = load i8, ptr %400, align 1
  %402 = icmp ne i8 %401, 0
  br i1 %402, label %403, label %404

403:                                              ; preds = %388
  call void @__asan_report_load8(i64 %397) #5     ; ####### line 119, checking temp->pred
  unreachable

404:                                              ; preds = %388
  %405 = load ptr, ptr %pred69, align 8
  store ptr %405, ptr %father, align 8
  br label %while.cond, !llvm.loop !8

while.end:                                        ; preds = %while.cond
  %406 = load i64, ptr %delta.addr, align 8
  %407 = load i64, ptr %feas_tol.addr, align 8
  %cmp70 = icmp sgt i64 %406, %407
  br i1 %cmp70, label %if.then72, label %if.else109

if.then72:                                        ; preds = %while.end
  %408 = load ptr, ptr %jminus.addr, align 8
  store ptr %408, ptr %temp, align 8
  br label %for.cond

for.cond:                                         ; preds = %468, %if.then72
  %409 = load ptr, ptr %temp, align 8
  %410 = load ptr, ptr %w.addr, align 8
  %cmp73 = icmp ne ptr %409, %410
  br i1 %cmp73, label %for.body, label %for.end

for.body:                                         ; preds = %for.cond
  %411 = load i64, ptr %depth_iminus, align 8
  %412 = load ptr, ptr %temp, align 8
  %depth75 = getelementptr inbounds nuw %struct.node, ptr %412, i32 0, i32 11
  %413 = ptrtoint ptr %depth75 to i64
  %414 = lshr i64 %413, 3
  %415 = add i64 %414, 2147450880
  %416 = inttoptr i64 %415 to ptr
  %417 = load i8, ptr %416, align 1
  %418 = icmp ne i8 %417, 0
  br i1 %418, label %419, label %420

419:                                              ; preds = %for.body
  call void @__asan_report_load8(i64 %413) #5     ; ####### line 126, checking temp->depth
  unreachable

420:                                              ; preds = %for.body
  %421 = load i64, ptr %depth75, align 8
  %sub76 = sub nsw i64 %421, %411
  store i64 %sub76, ptr %depth75, align 8
  %422 = load ptr, ptr %temp, align 8
  %orientation77 = getelementptr inbounds nuw %struct.node, ptr %422, i32 0, i32 1
  %423 = ptrtoint ptr %orientation77 to i64
  %424 = lshr i64 %423, 3
  %425 = add i64 %424, 2147450880
  %426 = inttoptr i64 %425 to ptr
  %427 = load i8, ptr %426, align 1
  %428 = icmp ne i8 %427, 0
  br i1 %428, label %429, label %435, !prof !7

429:                                              ; preds = %420
  %430 = and i64 %423, 7
  %431 = add i64 %430, 3
  %432 = trunc i64 %431 to i8
  %433 = icmp sge i8 %432, %427
  br i1 %433, label %434, label %435

434:                                              ; preds = %429
  call void @__asan_report_load4(i64 %423) #5     ; ####### line 127, checking temp->orientation
  unreachable

435:                                              ; preds = %429, %420
  %436 = load i32, ptr %orientation77, align 8
  %conv78 = sext i32 %436 to i64
  %437 = load i64, ptr %cycle_ori.addr, align 8
  %cmp79 = icmp ne i64 %conv78, %437
  br i1 %cmp79, label %if.then81, label %if.else84

if.then81:                                        ; preds = %435
  %438 = load i64, ptr %delta.addr, align 8
  %439 = load ptr, ptr %temp, align 8
  %flow82 = getelementptr inbounds nuw %struct.node, ptr %439, i32 0, i32 10
  %440 = ptrtoint ptr %flow82 to i64
  %441 = lshr i64 %440, 3
  %442 = add i64 %441, 2147450880
  %443 = inttoptr i64 %442 to ptr
  %444 = load i8, ptr %443, align 1
  %445 = icmp ne i8 %444, 0
  br i1 %445, label %446, label %447

446:                                              ; preds = %if.then81
  call void @__asan_report_load8(i64 %440) #5     ; ####### line 128, checking temp->flow
  unreachable

447:                                              ; preds = %if.then81
  %448 = load i64, ptr %flow82, align 8
  %add83 = add nsw i64 %448, %438
  store i64 %add83, ptr %flow82, align 8
  br label %if.end87

if.else84:                                        ; preds = %435
  %449 = load i64, ptr %delta.addr, align 8
  %450 = load ptr, ptr %temp, align 8
  %flow85 = getelementptr inbounds nuw %struct.node, ptr %450, i32 0, i32 10
  %451 = ptrtoint ptr %flow85 to i64
  %452 = lshr i64 %451, 3
  %453 = add i64 %452, 2147450880
  %454 = inttoptr i64 %453 to ptr
  %455 = load i8, ptr %454, align 1
  %456 = icmp ne i8 %455, 0
  br i1 %456, label %457, label %458

457:                                              ; preds = %if.else84
  call void @__asan_report_load8(i64 %451) #5     ; ####### line 130, checking temp->flow
  unreachable

458:                                              ; preds = %if.else84
  %459 = load i64, ptr %flow85, align 8
  %sub86 = sub nsw i64 %459, %449
  store i64 %sub86, ptr %flow85, align 8
  br label %if.end87

if.end87:                                         ; preds = %458, %447
  br label %for.inc

for.inc:                                          ; preds = %if.end87
  %460 = load ptr, ptr %temp, align 8
  %pred88 = getelementptr inbounds nuw %struct.node, ptr %460, i32 0, i32 3
  %461 = ptrtoint ptr %pred88 to i64
  %462 = lshr i64 %461, 3
  %463 = add i64 %462, 2147450880
  %464 = inttoptr i64 %463 to ptr
  %465 = load i8, ptr %464, align 1
  %466 = icmp ne i8 %465, 0
  br i1 %466, label %467, label %468

467:                                              ; preds = %for.inc
  call void @__asan_report_load8(i64 %461) #5     ; ####### line 124, checking temp->pred
  unreachable

468:                                              ; preds = %for.inc
  %469 = load ptr, ptr %pred88, align 8
  store ptr %469, ptr %temp, align 8
  br label %for.cond, !llvm.loop !10

for.end:                                          ; preds = %for.cond
  %470 = load ptr, ptr %jplus.addr, align 8
  store ptr %470, ptr %temp, align 8
  br label %for.cond89

for.cond89:                                       ; preds = %530, %for.end
  %471 = load ptr, ptr %temp, align 8
  %472 = load ptr, ptr %w.addr, align 8
  %cmp90 = icmp ne ptr %471, %472
  br i1 %cmp90, label %for.body92, label %for.end108

for.body92:                                       ; preds = %for.cond89
  %473 = load i64, ptr %depth_iminus, align 8
  %474 = load ptr, ptr %temp, align 8
  %depth93 = getelementptr inbounds nuw %struct.node, ptr %474, i32 0, i32 11
  %475 = ptrtoint ptr %depth93 to i64
  %476 = lshr i64 %475, 3
  %477 = add i64 %476, 2147450880
  %478 = inttoptr i64 %477 to ptr
  %479 = load i8, ptr %478, align 1
  %480 = icmp ne i8 %479, 0
  br i1 %480, label %481, label %482

481:                                              ; preds = %for.body92
  call void @__asan_report_load8(i64 %475) #5     ; ####### line 134, checking temp->depth
  unreachable

482:                                              ; preds = %for.body92
  %483 = load i64, ptr %depth93, align 8
  %add94 = add nsw i64 %483, %473
  store i64 %add94, ptr %depth93, align 8
  %484 = load ptr, ptr %temp, align 8
  %orientation95 = getelementptr inbounds nuw %struct.node, ptr %484, i32 0, i32 1
  %485 = ptrtoint ptr %orientation95 to i64
  %486 = lshr i64 %485, 3
  %487 = add i64 %486, 2147450880
  %488 = inttoptr i64 %487 to ptr
  %489 = load i8, ptr %488, align 1
  %490 = icmp ne i8 %489, 0
  br i1 %490, label %491, label %497, !prof !7

491:                                              ; preds = %482
  %492 = and i64 %485, 7
  %493 = add i64 %492, 3
  %494 = trunc i64 %493 to i8
  %495 = icmp sge i8 %494, %489
  br i1 %495, label %496, label %497

496:                                              ; preds = %491
  call void @__asan_report_load4(i64 %485) #5     ; ####### line 135, checking temp->orientation
  unreachable

497:                                              ; preds = %491, %482
  %498 = load i32, ptr %orientation95, align 8
  %conv96 = sext i32 %498 to i64
  %499 = load i64, ptr %cycle_ori.addr, align 8
  %cmp97 = icmp eq i64 %conv96, %499
  br i1 %cmp97, label %if.then99, label %if.else102

if.then99:                                        ; preds = %497
  %500 = load i64, ptr %delta.addr, align 8
  %501 = load ptr, ptr %temp, align 8
  %flow100 = getelementptr inbounds nuw %struct.node, ptr %501, i32 0, i32 10
  %502 = ptrtoint ptr %flow100 to i64
  %503 = lshr i64 %502, 3
  %504 = add i64 %503, 2147450880
  %505 = inttoptr i64 %504 to ptr
  %506 = load i8, ptr %505, align 1
  %507 = icmp ne i8 %506, 0
  br i1 %507, label %508, label %509

508:                                              ; preds = %if.then99
  call void @__asan_report_load8(i64 %502) #5     ; ####### line 136, checking temp->flow
  unreachable

509:                                              ; preds = %if.then99
  %510 = load i64, ptr %flow100, align 8
  %add101 = add nsw i64 %510, %500
  store i64 %add101, ptr %flow100, align 8
  br label %if.end105

if.else102:                                       ; preds = %497
  %511 = load i64, ptr %delta.addr, align 8
  %512 = load ptr, ptr %temp, align 8
  %flow103 = getelementptr inbounds nuw %struct.node, ptr %512, i32 0, i32 10
  %513 = ptrtoint ptr %flow103 to i64
  %514 = lshr i64 %513, 3
  %515 = add i64 %514, 2147450880
  %516 = inttoptr i64 %515 to ptr
  %517 = load i8, ptr %516, align 1
  %518 = icmp ne i8 %517, 0
  br i1 %518, label %519, label %520

519:                                              ; preds = %if.else102
  call void @__asan_report_load8(i64 %513) #5     ; ####### line 138, checking temp->flow
  unreachable

520:                                              ; preds = %if.else102
  %521 = load i64, ptr %flow103, align 8
  %sub104 = sub nsw i64 %521, %511
  store i64 %sub104, ptr %flow103, align 8
  br label %if.end105

if.end105:                                        ; preds = %520, %509
  br label %for.inc106

for.inc106:                                       ; preds = %if.end105
  %522 = load ptr, ptr %temp, align 8
  %pred107 = getelementptr inbounds nuw %struct.node, ptr %522, i32 0, i32 3
  %523 = ptrtoint ptr %pred107 to i64
  %524 = lshr i64 %523, 3
  %525 = add i64 %524, 2147450880
  %526 = inttoptr i64 %525 to ptr
  %527 = load i8, ptr %526, align 1
  %528 = icmp ne i8 %527, 0
  br i1 %528, label %529, label %530

529:                                              ; preds = %for.inc106
  call void @__asan_report_load8(i64 %523) #5     ; ####### line 132, checking temp->pred
  unreachable

530:                                              ; preds = %for.inc106
  %531 = load ptr, ptr %pred107, align 8
  store ptr %531, ptr %temp, align 8
  br label %for.cond89, !llvm.loop !11

for.end108:                                       ; preds = %for.cond89
  br label %if.end128

if.else109:                                       ; preds = %while.end
  %532 = load ptr, ptr %jminus.addr, align 8
  store ptr %532, ptr %temp, align 8
  br label %for.cond110

for.cond110:                                      ; preds = %554, %if.else109
  %533 = load ptr, ptr %temp, align 8
  %534 = load ptr, ptr %w.addr, align 8
  %cmp111 = icmp ne ptr %533, %534
  br i1 %cmp111, label %for.body113, label %for.end118

for.body113:                                      ; preds = %for.cond110
  %535 = load i64, ptr %depth_iminus, align 8
  %536 = load ptr, ptr %temp, align 8
  %depth114 = getelementptr inbounds nuw %struct.node, ptr %536, i32 0, i32 11
  %537 = ptrtoint ptr %depth114 to i64
  %538 = lshr i64 %537, 3
  %539 = add i64 %538, 2147450880
  %540 = inttoptr i64 %539 to ptr
  %541 = load i8, ptr %540, align 1
  %542 = icmp ne i8 %541, 0
  br i1 %542, label %543, label %544

543:                                              ; preds = %for.body113
  call void @__asan_report_load8(i64 %537) #5     ; ####### line 144, checking temp->depth
  unreachable

544:                                              ; preds = %for.body113
  %545 = load i64, ptr %depth114, align 8
  %sub115 = sub nsw i64 %545, %535
  store i64 %sub115, ptr %depth114, align 8
  br label %for.inc116

for.inc116:                                       ; preds = %544
  %546 = load ptr, ptr %temp, align 8
  %pred117 = getelementptr inbounds nuw %struct.node, ptr %546, i32 0, i32 3
  %547 = ptrtoint ptr %pred117 to i64
  %548 = lshr i64 %547, 3
  %549 = add i64 %548, 2147450880
  %550 = inttoptr i64 %549 to ptr
  %551 = load i8, ptr %550, align 1
  %552 = icmp ne i8 %551, 0
  br i1 %552, label %553, label %554

553:                                              ; preds = %for.inc116
  call void @__asan_report_load8(i64 %547) #5     ; ####### line 143, checking temp->pred
  unreachable

554:                                              ; preds = %for.inc116
  %555 = load ptr, ptr %pred117, align 8
  store ptr %555, ptr %temp, align 8
  br label %for.cond110, !llvm.loop !12

for.end118:                                       ; preds = %for.cond110
  %556 = load ptr, ptr %jplus.addr, align 8
  store ptr %556, ptr %temp, align 8
  br label %for.cond119

for.cond119:                                      ; preds = %578, %for.end118
  %557 = load ptr, ptr %temp, align 8
  %558 = load ptr, ptr %w.addr, align 8
  %cmp120 = icmp ne ptr %557, %558
  br i1 %cmp120, label %for.body122, label %for.end127

for.body122:                                      ; preds = %for.cond119
  %559 = load i64, ptr %depth_iminus, align 8
  %560 = load ptr, ptr %temp, align 8
  %depth123 = getelementptr inbounds nuw %struct.node, ptr %560, i32 0, i32 11
  %561 = ptrtoint ptr %depth123 to i64
  %562 = lshr i64 %561, 3
  %563 = add i64 %562, 2147450880
  %564 = inttoptr i64 %563 to ptr
  %565 = load i8, ptr %564, align 1
  %566 = icmp ne i8 %565, 0
  br i1 %566, label %567, label %568

567:                                              ; preds = %for.body122
  call void @__asan_report_load8(i64 %561) #5     ; ####### line 146, checking temp->depth
  unreachable

568:                                              ; preds = %for.body122
  %569 = load i64, ptr %depth123, align 8
  %add124 = add nsw i64 %569, %559
  store i64 %add124, ptr %depth123, align 8
  br label %for.inc125

for.inc125:                                       ; preds = %568
  %570 = load ptr, ptr %temp, align 8
  %pred126 = getelementptr inbounds nuw %struct.node, ptr %570, i32 0, i32 3
  %571 = ptrtoint ptr %pred126 to i64
  %572 = lshr i64 %571, 3
  %573 = add i64 %572, 2147450880
  %574 = inttoptr i64 %573 to ptr
  %575 = load i8, ptr %574, align 1
  %576 = icmp ne i8 %575, 0
  br i1 %576, label %577, label %578

577:                                              ; preds = %for.inc125
  call void @__asan_report_load8(i64 %571) #5     ; ####### line 145, checking temp->pred
  unreachable

578:                                              ; preds = %for.inc125
  %579 = load ptr, ptr %pred126, align 8
  store ptr %579, ptr %temp, align 8
  br label %for.cond119, !llvm.loop !13

for.end127:                                       ; preds = %for.cond119
  br label %if.end128

if.end128:                                        ; preds = %for.end127, %for.end108
  call void @llvm.lifetime.end.p0(i64 8, ptr %flow_temp) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %new_depth) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %depth_iminus) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %depth_temp) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %orientation_temp) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %new_pred) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %temp) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %father) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %new_basic_arc) #4
  call void @llvm.lifetime.end.p0(i64 8, ptr %basic_arc_temp) #4
  ret void
}
