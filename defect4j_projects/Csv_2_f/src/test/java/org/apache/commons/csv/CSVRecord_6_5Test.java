package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_6_5Test {

    private CSVRecord csvRecord;
    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    void setUp() {
        mapping = new HashMap<>();
        values = new String[] { "val0", "val1", "val2" };
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexLessThanValuesLength() throws Exception {
        mapping.put("name", 1);
        csvRecord = new CSVRecord(values, mapping, null, 1L);

        // Use reflection to invoke public method isMapped to confirm it works as expected
        Method isMappedMethod = CSVRecord.class.getMethod("isMapped", String.class);
        boolean mapped = (boolean) isMappedMethod.invoke(csvRecord, "name");
        assertTrue(mapped);

        // Test isSet returns true when mapped and index < values.length
        assertTrue(csvRecord.isSet("name"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexEqualToValuesLength() {
        mapping.put("name", values.length);
        csvRecord = new CSVRecord(values, mapping, null, 1L);

        // isSet should return false because index == values.length
        assertFalse(csvRecord.isSet("name"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameMappedAndIndexGreaterThanValuesLength() {
        mapping.put("name", values.length + 1);
        csvRecord = new CSVRecord(values, mapping, null, 1L);

        // isSet should return false because index > values.length
        assertFalse(csvRecord.isSet("name"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nameNotMapped() {
        // mapping is empty, so isMapped returns false
        csvRecord = new CSVRecord(values, mapping, null, 1L);

        assertFalse(csvRecord.isSet("name"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_nullName() {
        mapping.put("name", 0);
        csvRecord = new CSVRecord(values, mapping, null, 1L);

        // Passing null name, isMapped should return false, so isSet false
        assertFalse(csvRecord.isSet(null));
    }
}