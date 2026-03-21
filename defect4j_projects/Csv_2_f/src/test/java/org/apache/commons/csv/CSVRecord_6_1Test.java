package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_6_1Test {

    private CSVRecord csvRecord;
    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    void setUp() {
        values = new String[] { "value0", "value1", "value2" };
        mapping = new HashMap<>();
        mapping.put("col0", 0);
        mapping.put("col1", 1);
        mapping.put("col2", 2);
        csvRecord = new CSVRecord(values, mapping, null, 1L);
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexInRange() {
        assertTrue(csvRecord.isSet("col0"));
        assertTrue(csvRecord.isSet("col1"));
        assertTrue(csvRecord.isSet("col2"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedButIndexOutOfRange() {
        mapping.put("col3", 3); // index 3 not in values length 3
        // recreate csvRecord to reflect updated mapping
        csvRecord = new CSVRecord(values, mapping, null, 1L);
        assertFalse(csvRecord.isSet("col3"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameNotMapped() {
        assertFalse(csvRecord.isSet("nonExistingColumn"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_withNullName() {
        assertFalse(csvRecord.isSet(null));
    }

    @Test
    @Timeout(8000)
    void testIsSet_whenMappingIsEmpty() {
        CSVRecord record = new CSVRecord(values, Collections.emptyMap(), null, 1L);
        assertFalse(record.isSet("col0"));
    }

    @Test
    @Timeout(8000)
    void testIsMapped_privateMethod_viaReflection() throws Exception {
        Method isMappedMethod = CSVRecord.class.getDeclaredMethod("isMapped", String.class);
        isMappedMethod.setAccessible(true);

        assertTrue((boolean) isMappedMethod.invoke(csvRecord, "col0"));
        assertFalse((boolean) isMappedMethod.invoke(csvRecord, "nonExistingColumn"));
        assertFalse((boolean) isMappedMethod.invoke(csvRecord, (Object) null));
    }
}