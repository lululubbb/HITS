package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.lang.reflect.Method;
import java.util.Map;

class CSVRecord_8_6Test {

    @Test
    @Timeout(8000)
    void testValuesMethod() throws Exception {
        String[] vals = new String[]{"a", "b", "c"};
        Map<String, Integer> mapping = Mockito.mock(Map.class);
        String comment = "comment";
        long recordNumber = 123L;

        // Use the package-private constructor directly since the test is in the same package
        CSVRecord record = new CSVRecord(vals, mapping, comment, recordNumber);

        Method valuesMethod = CSVRecord.class.getDeclaredMethod("values");
        valuesMethod.setAccessible(true);
        String[] returnedValues = (String[]) valuesMethod.invoke(record);

        assertArrayEquals(vals, returnedValues);
    }
}